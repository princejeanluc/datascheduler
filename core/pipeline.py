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


def is_cancel_requested(pipeline_id: int) -> bool:
    """
    Indique si un arrêt a été demandé pour le run en cours de ce pipeline mais n'a pas
    encore abouti (l'étape en cours n'a pas encore atteint sa prochaine limite) — utilisé
    par l'UI pour afficher un état "Arrêt en cours" plutôt que de laisser l'utilisateur
    sans retour visuel après avoir demandé une interruption (voir PipelinesView.refresh()).
    """
    with _active_runs_lock:
        event = _active_runs.get(pipeline_id)
    return bool(event and event.is_set())


# ──────────────────────────────────────────────
#  VALIDATION STATIQUE D'UNE SÉQUENCE D'ÉTAPES
# ──────────────────────────────────────────────

def _duplicate_output_name_errors(steps: list[dict]) -> list[str]:
    """
    Un nom de sortie personnalisé (config["output_name"]/["output_names"] — voir
    core/pipeline.py, publication d'alias en plus de _step_key) utilisé par plusieurs étapes
    du même pipeline se marcherait dessus dans ctx.artifacts. Partagé par
    validate_step_sequence() et validate_pipeline_graph() — même règle dans les deux éditeurs.
    """
    seen: dict[str, list[str]] = {}
    for step in steps:
        label = step.get("label") or step.get("step_type", "")
        config = step.get("config") or {}
        names = []
        if config.get("output_name"):
            names.append(config["output_name"])
        names.extend(config.get("output_names") or [])
        for name in names:
            seen.setdefault(name, []).append(label)

    errors = []
    for name, labels in seen.items():
        if len(labels) > 1:
            errors.append(
                f"Le nom de sortie « {name} » est utilisé par plusieurs étapes "
                f"({', '.join(labels)}) — chaque nom doit être unique dans le pipeline."
            )
    return errors

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

    errors.extend(_duplicate_output_name_errors(steps))
    return errors, warnings


# ──────────────────────────────────────────────
#  EXÉCUTION LINÉAIRE (comportement historique, inchangé)
# ──────────────────────────────────────────────

def _execute_linear(steps, ctx, progress, result, cancel_event) -> tuple[bool, bool]:
    """
    Boucle d'exécution actuelle, extraite telle quelle de run_pipeline() — chemin emprunté
    pour tout pipeline sans arête explicite (`db.get_edges()` vide), donc pour tous les
    pipelines existants et pour l'éditeur linéaire (PipelineEditorDialog), inchangés par le
    chantier 6a. Retourne (pipeline_failed, pipeline_cancelled).
    """
    total = len(steps)
    pipeline_failed  = False
    pipeline_cancelled = False

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
            # Alias cosmétique en plus (chantier UX — ports nommés) : ne remplace jamais la
            # publication sous step_key ci-dessus, qui reste seule responsable du câblage
            # réel (arêtes, reads_from_step_key). Renommer output_name ne casse donc jamais
            # le graphe — seul un script/token qui référençait l'ancien nom cesse de le
            # trouver, un échec visible plutôt qu'une corruption silencieuse.
            output_name = config.get("output_name")
            if output_name:
                ctx.artifacts[output_name] = ctx.output_file

        if not step_result.success:
            if not pipeline_failed:
                ctx.extra["failed_step_label"] = step_label
                ctx.extra["error_message"]     = step_result.error
                result.fail(f"Étape {i + 1} ({step_label}) : {step_result.error}")
                pipeline_failed = True
            elif step.run_always:
                result.log(f"Étape 'toujours exécutée' {i + 1} ({step_label}) en échec : {step_result.error}")

    return pipeline_failed, pipeline_cancelled


# ──────────────────────────────────────────────
#  EXÉCUTION EN GRAPHE (chantier 6a)
# ──────────────────────────────────────────────

def _topological_order(steps, edges):
    """
    Ordre topologique des étapes (algorithme de Kahn) sur les `_step_key` référencés par les
    arêtes. Tie-break déterministe par `step_order` (ordre d'édition/création). Les étapes sans
    `_step_key` (ne peuvent avoir aucune arête) sont ajoutées à la fin dans leur step_order
    d'origine — cas résiduel, chaque étape enregistrée via _BaseStepConfigDialog.result_step()
    reçoit toujours une clé.

    Retourne None si le graphe contient un cycle.
    """
    configs = {id(s): json.loads(s.config_json or "{}") for s in steps}
    by_key  = {}
    key_order = {}
    for s in steps:
        key = configs[id(s)].get("_step_key")
        if key:
            by_key[key] = s
            key_order[key] = s.step_order

    incoming: dict = {k: [] for k in by_key}
    outgoing: dict = {k: [] for k in by_key}
    for e in edges:
        if e.from_step_key in by_key and e.to_step_key in by_key:
            incoming[e.to_step_key].append(e.from_step_key)
            outgoing[e.from_step_key].append(e.to_step_key)

    in_degree = {k: len(v) for k, v in incoming.items()}
    ready = [k for k, d in in_degree.items() if d == 0]
    ordered_keys: list[str] = []

    while ready:
        ready.sort(key=lambda k: key_order[k])
        k = ready.pop(0)
        ordered_keys.append(k)
        for nxt in outgoing[k]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                ready.append(nxt)

    if len(ordered_keys) != len(by_key):
        return None   # cycle détecté

    keyless = sorted(
        (s for s in steps if not configs[id(s)].get("_step_key")),
        key=lambda s: s.step_order,
    )
    return [by_key[k] for k in ordered_keys] + keyless


def _execute_graph(steps, edges, ctx, progress, result, cancel_event) -> tuple[bool, bool]:
    """
    Exécution en ordre topologique. L'échec d'une étape ne bloque que ses dépendants (directs ou
    indirects) — les branches indépendantes continuent. Un nœud à ports multiples (ex:
    ConditionStep) détermine, via `StepResult.active_port`, quelle(s) arête(s) sortante(s) sont
    actives — les autres sont traitées comme une branche non sélectionnée (skip, pas un échec).
    """
    order = _topological_order(steps, edges)
    if order is None:
        result.fail("Le graphe de ce pipeline contient un cycle — exécution impossible.")
        return True, False

    total = len(order)
    configs  = {id(s): json.loads(s.config_json or "{}") for s in order}
    key_of   = {id(s): configs[id(s)].get("_step_key") for s in order}

    incoming_by_key: dict = {}
    for e in edges:
        incoming_by_key.setdefault(e.to_step_key, []).append(e)

    step_status: dict = {}    # step_key -> "success" | "failed" | "skipped"
    active_port: dict = {}    # step_key -> port actif (steps à ports multiples)
    pipeline_failed    = False
    pipeline_cancelled = False

    for i, step in enumerate(order):
        if cancel_event.is_set():
            pipeline_cancelled = True
            result.fail("Exécution interrompue par l'utilisateur.")
            break

        step_type  = str(step.step_type).replace("StepType.", "")
        step_label = step.label or step_type
        config     = configs[id(step)]
        step_key   = key_of[id(step)]

        incoming    = incoming_by_key.get(step_key, []) if step_key else []
        unavailable = []
        for e in incoming:
            src_status = step_status.get(e.from_step_key)
            if src_status in ("failed", "skipped"):
                unavailable.append(e)
                continue
            src_active_port = active_port.get(e.from_step_key)
            if src_active_port is not None and e.from_port != src_active_port:
                unavailable.append(e)   # branche non sélectionnée par un nœud Condition en amont

        base_pct = int(i * 90 / total)
        next_pct = int((i + 1) * 90 / total)

        should_skip = bool(incoming) and len(unavailable) == len(incoming) and not step.run_always
        if should_skip:
            if step_key:
                step_status[step_key] = "skipped"
            failed_upstream = any(
                step_status.get(e.from_step_key) in ("failed", "skipped") for e in unavailable
            )
            reason = "dépendance en échec" if failed_upstream else "branche non sélectionnée"
            result.log(f"--- Étape {i + 1}/{total} : {step_label} ignorée ({reason}) ---")
            progress(f"Étape {i + 1}/{total} : {step_label} (ignorée)", next_pct)
            continue

        # Réoriente ctx.output_file vers l'artefact de la source, si une unique arête de donnée
        # entrante active existe — généralisation exacte de reads_from_step_key (chantier 3),
        # pilotée ici par la table d'arêtes plutôt que par le champ de config.
        data_incoming = [e for e in incoming if e not in unavailable]
        if len(data_incoming) == 1:
            ctx.output_file = ctx.artifacts.get(data_incoming[0].from_step_key)

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

            for line in ctx.log_lines:
                result.log_lines.append(line)
            ctx.log_lines.clear()

            if step_result.success or attempt >= retry_count:
                break
            attempt += 1
            result.log(f"Tentative {attempt}/{retry_count} après échec : {step_result.error}")
            time.sleep(RETRY_DELAY_S)

        if step_result.success:
            _, produces = get_step_requirements(step_type)
            if "output_file" in produces and step_key:
                ctx.artifacts[step_key] = ctx.output_file
            output_name = config.get("output_name")
            if output_name:
                ctx.artifacts[output_name] = ctx.output_file
            if step_key:
                step_status[step_key] = "success"
                if step_result.active_port:
                    active_port[step_key] = step_result.active_port
        else:
            if step_key:
                step_status[step_key] = "failed"
            pipeline_failed = True
            result.log(f"Étape {i + 1} ({step_label}) en échec : {step_result.error}")
            if not ctx.extra.get("failed_step_label"):
                ctx.extra["failed_step_label"] = step_label
                ctx.extra["error_message"]     = step_result.error
                result.fail(f"Étape {i + 1} ({step_label}) : {step_result.error}")

    return pipeline_failed, pipeline_cancelled


# ──────────────────────────────────────────────
#  VALIDATION STATIQUE D'UN GRAPHE (chantier 6a)
# ──────────────────────────────────────────────

def validate_pipeline_graph(steps: list[dict], edges: list[dict]) -> tuple[list[str], list[str]]:
    """
    Équivalent graphe de validate_step_sequence(), pour le futur éditeur graphique (6b) — steps
    et edges en dicts en mémoire, avant toute sauvegarde en base (même moment d'appel que
    validate_step_sequence() dans PipelineEditorDialog._on_save()).

    Détecte les cycles (algorithme de Kahn — si tous les nœuds n'atteignent pas un in-degree de
    0, cycle) puis vérifie que chaque étape dont REQUIRES est non vide a au moins une arête
    entrante — plus besoin du repli heuristique "dernière production" de validate_step_sequence :
    dans un graphe, l'arête EST la déclaration explicite de la source.
    """
    errors: list[str] = []
    warnings: list[str] = []

    by_key = {}
    for s in steps:
        key = (s.get("config") or {}).get("_step_key")
        if key:
            by_key[key] = s

    incoming: dict = {k: [] for k in by_key}
    in_degree: dict = {k: 0 for k in by_key}
    for e in edges:
        if e.get("from_step_key") in by_key and e.get("to_step_key") in by_key:
            incoming[e["to_step_key"]].append(e)
            in_degree[e["to_step_key"]] += 1

    ready = [k for k, d in in_degree.items() if d == 0]
    visited = 0
    outgoing: dict = {k: [] for k in by_key}
    for e in edges:
        if e.get("from_step_key") in by_key and e.get("to_step_key") in by_key:
            outgoing[e["from_step_key"]].append(e["to_step_key"])
    remaining = dict(in_degree)
    while ready:
        k = ready.pop()
        visited += 1
        for nxt in outgoing[k]:
            remaining[nxt] -= 1
            if remaining[nxt] == 0:
                ready.append(nxt)

    if visited != len(by_key):
        errors.append("Le graphe contient un cycle — impossible de déterminer un ordre d'exécution.")
        return errors, warnings

    for key, step in by_key.items():
        step_type  = step.get("step_type", "")
        label      = step.get("label") or step_type
        run_always = bool(step.get("run_always"))
        requires, _ = get_step_requirements(step_type)
        if requires and not incoming.get(key):
            msg = f"Étape « {label} » : nécessite {', '.join(sorted(requires))}, aucune arête entrante."
            (warnings if run_always else errors).append(msg)

    errors.extend(_duplicate_output_name_errors(steps))
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
        cancel_event = threading.Event()
        with _active_runs_lock:
            _active_runs[pipeline_id] = cancel_event

        # ── Exécution des étapes ──────────────────
        # Chemin DAG (chantier 6a) seulement si ce pipeline a des arêtes explicites (enregistré
        # au moins une fois via le futur éditeur graphique) — sinon la boucle linéaire actuelle,
        # inchangée : zéro changement de comportement pour tous les pipelines existants.
        edges = db.get_edges(pipeline_id)
        if edges:
            pipeline_failed, pipeline_cancelled = _execute_graph(
                steps, edges, ctx, progress, result, cancel_event
            )
        else:
            pipeline_failed, pipeline_cancelled = _execute_linear(
                steps, ctx, progress, result, cancel_event
            )

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
