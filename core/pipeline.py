"""
DataScheduler — core/pipeline.py
Exécuteur de pipeline : itère sur les PipelineStep dans l'ordre et passe le contexte.
"""

import json
import logging
from datetime import datetime

from database import db_manager as db
from core.steps import get_step, StepContext

logger = logging.getLogger(__name__)


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

        # ── Contexte partagé ──────────────────────
        ctx   = StepContext()
        total = len(steps)

        # ── Exécution des étapes ──────────────────
        for i, step in enumerate(steps):
            step_type  = str(step.step_type).replace("StepType.", "")
            step_label = step.label or step_type
            config     = json.loads(step.config_json or "{}")

            base_pct = int(i * 90 / total)       # 0 → 90 %
            next_pct = int((i + 1) * 90 / total)

            def step_progress(msg: str, pct: int, _bp=base_pct, _np=next_pct):
                scaled = _bp + int(pct * (_np - _bp) / 100)
                progress(msg, scaled)

            progress(f"Étape {i + 1}/{total} : {step_label}", base_pct)
            result.log(f"--- Étape {i + 1}/{total} : {step_label} ({step_type}) ---")

            executor     = get_step(step_type, config)
            step_result  = executor.run(ctx, on_progress=step_progress)

            # Récupération des logs accumulés dans le contexte
            for line in ctx.log_lines:
                result.log_lines.append(line)
            ctx.log_lines.clear()

            if not step_result.success:
                result.fail(f"Étape {i + 1} ({step_label}) : {step_result.error}")
                _update_run(run_id, "FAILED", result)
                result.finish(); return result

        # ── Nettoyage du fichier temporaire ───────
        if ctx.output_file and ctx.output_file.exists():
            try:
                ctx.output_file.unlink()
                result.log("Fichier temporaire supprimé.")
            except Exception as e:
                result.log(f"Avertissement : impossible de supprimer le tmp : {e}")

        # ── Succès ────────────────────────────────
        result.success       = True
        result.rows_exported = ctx.rows_count
        result.remote_path   = ctx.extra.get("remote_path") or ctx.extra.get("local_path")
        result.finish()
        progress("Terminé ✓", 100)
        result.log(
            f"Pipeline terminé en {result.duration_s:.1f}s"
            + (f" — {result.rows_exported:,} lignes exportées." if result.rows_exported else ".")
        )
        _update_run(run_id, "SUCCESS", result)
        _update_pipeline_status(pipeline_id, "SUCCESS")
        return result

    except Exception as e:
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
