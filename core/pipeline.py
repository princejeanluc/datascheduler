"""
DataScheduler — core/pipeline.py
Exécuteur de pipeline : itère sur les PipelineStep dans l'ordre et passe le contexte.
"""

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from database import db_manager as db
from core.steps import get_step, get_step_requirements, StepContext

logger = logging.getLogger(__name__)

RETRY_DELAY_S = 5


# ──────────────────────────────────────────────
#  RÉSULTAT D'EXÉCUTION
# ──────────────────────────────────────────────

class PipelineResult:
    def __init__(self):
        self.success       = False
        self.rows_exported = 0
        self.remote_path   = None
        self.error         = None
        self.log_lines     = []
        self.started_at    = datetime.utcnow()
        self.finished_at   = None

    def log(self, msg: str):
        ts = datetime.utcnow().strftime("%H:%M:%S")
        self.log_lines.append(f"[{ts}] {msg}")
        logger.info(msg)

    def fail(self, msg: str):
        self.error = msg
        self.log(f"ERREUR : {msg}")

    def finish(self):
        self.finished_at = datetime.utcnow()

    @property
    def duration_s(self) -> float:
        if self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return 0.0

    @property
    def log_text(self) -> str:
        return "\n".join(self.log_lines)


# ──────────────────────────────────────────────
#  VERROU ANTI-CHEVAUCHEMENT (opt-in par pipeline)
# ──────────────────────────────────────────────

_active_runs: dict[int, threading.Event] = {}
_active_runs_lock = threading.Lock()


def is_pipeline_running(pipeline_id: int) -> bool:
    """Indique si un run de ce pipeline est actuellement en cours."""
    with _active_runs_lock:
        return pipeline_id in _active_runs


def request_cancel(pipeline_id: int) -> bool:
    """
    Demande l'arrêt coopératif d'un run en cours pour ce pipeline — effectif à la
    prochaine limite d'étape, pas instantanément. Retourne False si aucun run n'était
    en cours.
    """
    with _active_runs_lock:
        event = _active_runs.get(pipeline_id)
    if event is None:
        return False
    event.set()
    return True


# ──────────────────────────────────────────────
#  VALIDATION STATIQUE D'UNE SÉQUENCE D'ÉTAPES
# ──────────────────────────────────────────────

def validate_step_sequence(steps: list[dict]) -> tuple[list[str], list[str]]:
    """
    Simule la séquence d'étapes (sans rien exécuter) et vérifie que chaque étape trouve
    dans le contexte ce qu'elle REQUIRES, d'après ce que les étapes précédentes PRODUCES.

    Une étape peut cibler explicitement une source antérieure précise via
    config["reads_from_step_key"] (sélecteur "Source" de l'éditeur) — dans ce cas la
    vérification porte sur cette clé spécifique plutôt que sur le tag générique
    "output_file" (comportement par défaut, inchangé, quand aucune cible n'est choisie).

    Retourne (erreurs_bloquantes, avertissements) :
      - une étape normale dont un REQUIRES n'est pas satisfait → erreur bloquante.
      - une étape "toujours exécutée" (run_always) dans le même cas → avertissement
        seulement, car son contexte réel au moment de l'exécution est imprévisible
        (elle peut tourner après un échec précoce qui a empêché la production attendue).
    """
    errors: list[str] = []
    warnings: list[str] = []
    available: set[str] = set()
    available_keys: set[str] = set()

    for i, step in enumerate(steps):
        step_type  = step.get("step_type", "")
        label      = step.get("label") or step_type
        run_always = bool(step.get("run_always"))
        config     = step.get("config") or {}

        requires, produces = get_step_requirements(step_type)
        target_key = config.get("reads_from_step_key")

        if requires:
            if target_key:
                missing = target_key not in available_keys
                msg = (
                    f"Étape {i + 1} ({label}) : la source ciblée n'a pas encore été produite "
                    "à ce stade (étape supprimée, déplacée après, ou jamais réenregistrée)."
                )
            else:
                missing = bool(requires - available)
                msg = f"Étape {i + 1} ({label}) : nécessite {', '.join(sorted(requires))}, non garanti par les étapes précédentes."

            if missing:
                if run_always:
                    warnings.append(msg)
                else:
                    errors.append(msg)

        available |= produces
        step_key = config.get("_step_key")
        if produces and step_key:
            available_keys.add(step_key)

    return errors, warnings


# ──────────────────────────────────────────────
#  EXÉCUTEUR PRINCIPAL
# ──────────────────────────────────────────────

def run_pipeline(pipeline_id: int, on_progress=None) -> PipelineResult:
    """
    Exécute un pipeline en enchaînant ses PipelineStep dans l'ordre.
    Le contexte (fichier, nombre de lignes, etc.) est transmis d'étape en étape.

    Paramètres :
        pipeline_id  : ID du pipeline en base
        on_progress  : callback(step: str, pct: int) pour alimenter l'UI

    Retourne un PipelineResult (ne lève jamais d'exception).
    """
    result = PipelineResult()
    run_id = None

    def progress(msg: str, pct: int):
        if on_progress:
            on_progress(msg, pct)

    try:
        # ── Chargement ───────────────────────────
        progress("Chargement…", 0)
        pipeline = db.get_pipeline(pipeline_id)
        if not pipeline:
            result.fail(f"Pipeline ID {pipeline_id} introuvable.")
            result.finish(); return result

        # ── Verrou anti-chevauchement (opt-in) ────
        if pipeline.prevent_overlap and is_pipeline_running(pipeline_id):
            result.fail("Ignoré : ce pipeline est déjà en cours d'exécution.")
            result.finish()
            logger.warning("Pipeline %s : run ignoré (déjà en cours, prevent_overlap=True).", pipeline.name)
            return result

        steps = db.get_steps(pipeline_id)
        if not steps:
            result.fail("Ce pipeline ne contient aucune étape.")
            result.finish(); return result

        result.log(f"Pipeline : {pipeline.name} ({len(steps)} étape(s))")

        # ── Enregistrement du run ─────────────────
        run    = db.create_run(pipeline_id)
        run_id = run.id
        result.log(f"Run ID : {run_id}")
        _update_pipeline_status(pipeline_id, "RUNNING")

        # ── Contexte partagé + enregistrement du verrou ──
        ctx    = StepContext()
        total  = len(steps)
        cancel_event = threading.Event()
        with _active_runs_lock:
            _active_runs[pipeline_id] = cancel_event

        pipeline_failed  = False
        pipeline_cancelled = False

        # ── Exécution des étapes ──────────────────
        for i, step in enumerate(steps):
            if cancel_event.is_set():
                pipeline_cancelled = True
                result.fail("Exécution interrompue par l'utilisateur.")
                break

            step_type  = str(step.step_type).replace("StepType.", "")
            step_label = step.label or step_type
            config     = json.loads(step.config_json or "{}")

            if pipeline_failed and not step.run_always:
                continue

            # Ciblage explicite d'une source antérieure (sélecteur "Source" de l'éditeur) —
            # réoriente le slot par défaut avant l'exécution ; l'étape elle-même lit
            # ctx.output_file sans rien savoir de ce réaiguillage.
            target_key = config.get("reads_from_step_key")
            if target_key:
                ctx.output_file = ctx.artifacts.get(target_key)

            base_pct = int(i * 90 / total)       # 0 → 90 %
            next_pct = int((i + 1) * 90 / total)

            def step_progress(msg: str, pct: int, _bp=base_pct, _np=next_pct):
                scaled = _bp + int(pct * (_np - _bp) / 100)
                progress(msg, scaled)

            progress(f"Étape {i + 1}/{total} : {step_label}", base_pct)
            result.log(f"--- Étape {i + 1}/{total} : {step_label} ({step_type}) ---")

            executor    = get_step(step_type, config)
            retry_count = step.retry_count or 0
            attempt     = 0
            while True:
                step_result = executor.run(ctx, on_progress=step_progress)

                # Récupération des logs accumulés dans le contexte
                for line in ctx.log_lines:
                    result.log_lines.append(line)
                ctx.log_lines.clear()

                if step_result.success or attempt >= retry_count:
                    break
                attempt += 1
                result.log(f"Tentative {attempt}/{retry_count} après échec : {step_result.error}")
                time.sleep(RETRY_DELAY_S)

            if step_result.success:
                # Publie en plus sous la clé stable de CETTE étape, pour qu'une étape
                # consommatrice ultérieure puisse cibler explicitement "la sortie de
                # cette étape précise" plutôt que "la dernière produite" (voir
                # docs/ARCHITECTURE.md, section StepContext).
                _, produces = get_step_requirements(step_type)
                step_key = config.get("_step_key")
                if "output_file" in produces and step_key:
                    ctx.artifacts[step_key] = ctx.output_file

            if not step_result.success:
                if not pipeline_failed:
                    ctx.extra["failed_step_label"] = step_label
                    ctx.extra["error_message"]     = step_result.error
                    result.fail(f"Étape {i + 1} ({step_label}) : {step_result.error}")
                    pipeline_failed = True
                elif step.run_always:
                    result.log(f"Étape 'toujours exécutée' {i + 1} ({step_label}) en échec : {step_result.error}")

        # ── Nettoyage des fichiers temporaires (inconditionnel) ──
        # Plusieurs artefacts nommés peuvent désormais être vivants simultanément (ex : deux
        # DB_EXTRACT en amont de deux consommateurs différents) — le set déduplique le cas
        # courant où le même Path apparaît à la fois sous "output_file" et sous une clé
        # d'étape spécifique.
        temp_paths = {p for p in ctx.artifacts.values() if isinstance(p, Path)}
        for p in temp_paths:
            if p.exists():
                try:
                    p.unlink()
                    result.log(f"Fichier temporaire supprimé : {p}")
                except Exception as e:
                    result.log(f"Avertissement : impossible de supprimer le tmp {p} : {e}")

        with _active_runs_lock:
            _active_runs.pop(pipeline_id, None)

        # ── Issue ─────────────────────────────────
        result.finish()
        if pipeline_cancelled:
            _update_run(run_id, "CANCELLED", result)
            _update_pipeline_status(pipeline_id, "CANCELLED")
            return result

        if pipeline_failed:
            _update_run(run_id, "FAILED", result)
            _update_pipeline_status(pipeline_id, "FAILED")
            return result

        result.success       = True
        result.rows_exported = ctx.rows_count
        result.remote_path   = ctx.extra.get("remote_path") or ctx.extra.get("local_path")
        progress("Terminé ✓", 100)
        result.log(
            f"Pipeline terminé en {result.duration_s:.1f}s"
            + (f" — {result.rows_exported:,} lignes exportées." if result.rows_exported else ".")
        )
        _update_run(run_id, "SUCCESS", result)
        _update_pipeline_status(pipeline_id, "SUCCESS")
        return result

    except Exception as e:
        with _active_runs_lock:
            _active_runs.pop(pipeline_id, None)
        result.fail(f"Exception inattendue : {e}")
        result.finish()
        if run_id:
            _update_run(run_id, "FAILED", result)
        _update_pipeline_status(pipeline_id, "FAILED")
        logger.exception("Erreur pipeline %s", pipeline_id)
        return result


# ──────────────────────────────────────────────
#  HELPERS DB
# ──────────────────────────────────────────────

def _update_run(run_id: int, status: str, result: PipelineResult):
    db.finish_run(
        run_id,
        status=status,
        rows_exported=result.rows_exported,
        remote_path=result.remote_path,
        error_message=result.error,
        log_text=result.log_text,
    )


def _update_pipeline_status(pipeline_id: int, status: str):
    with db.get_session() as s:
        from database.models import Pipeline
        p = s.get(Pipeline, pipeline_id)
        if p:
            p.last_status = status
            p.last_run_at = datetime.utcnow()
