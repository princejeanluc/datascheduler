"""
DataScheduler — tests/test_concurrency_cap.py
Chantier suivi des ressources : AppSettings.max_concurrent_runs était stocké depuis le chantier
écran Paramètres, mais jamais appliqué — premier vrai usage du champ. run_pipeline() doit
refuser tout nouveau lancement au-delà du plafond, sans créer de ligne d'historique (même
patron que les autres refus anticipés déjà présents : pipeline introuvable, aucune étape).
"""

import threading

import core.pipeline as pipeline_module
import core.steps as steps_module
from core.pipeline import run_pipeline
from core.steps.base import BaseStep, StepResult
from database import db_manager as db


class _FakeStep(BaseStep):
    def run(self, ctx, on_progress=None):
        return StepResult(success=True)


def test_run_pipeline_refuses_above_concurrency_cap(test_db):
    db.update_app_settings(max_concurrent_runs=1)
    pipeline = db.create_pipeline(name="cap-test")
    db.save_steps(pipeline.id, [{"step_type": "DB_EXTRACT", "label": "A", "config": {}}])

    # Occupe le seul emplacement disponible — simule un autre pipeline déjà en cours, sans
    # dépendre d'un vrai thread concurrent.
    fake_event = threading.Event()
    pipeline_module._active_runs[999_999] = fake_event
    try:
        result = run_pipeline(pipeline.id)
    finally:
        pipeline_module._active_runs.pop(999_999, None)

    assert not result.success
    assert "Plafond d'exécutions simultanées atteint (1)" in result.error
    assert db.get_runs(pipeline.id) == []   # aucune ligne d'historique créée pour un refus


def test_run_pipeline_succeeds_when_under_concurrency_cap(test_db, monkeypatch):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeStep)
    db.update_app_settings(max_concurrent_runs=6)   # défaut — aucun run actif, largement sous le plafond

    pipeline = db.create_pipeline(name="under-cap-test")
    db.save_steps(pipeline.id, [{"step_type": "DB_EXTRACT", "label": "A", "config": {}}])

    result = run_pipeline(pipeline.id)

    assert result.success
    assert len(db.get_runs(pipeline.id)) == 1


def test_run_pipeline_refusal_message_does_not_mention_technical_internals(test_db):
    """Le message doit rester compréhensible pour un lancement manuel (affiché tel quel dans
    RunProgressDialog) ou planifié (remonté via le statut bar) — pas de jargon interne."""
    db.update_app_settings(max_concurrent_runs=0)
    pipeline = db.create_pipeline(name="cap-message-test")
    db.save_steps(pipeline.id, [{"step_type": "DB_EXTRACT", "label": "A", "config": {}}])

    result = run_pipeline(pipeline.id)

    assert not result.success
    assert "réessayez plus tard" in result.error
