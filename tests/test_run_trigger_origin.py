"""
DataScheduler — tests/test_run_trigger_origin.py
Lot D2-D4 (DONNEES.md::D2) : pipeline_runs.trigger_origin/triggered_by_run_id/scheduled_for.
Le cas TRIGGERED (avec triggered_by_run_id) est déjà couvert par
tests/test_pipeline_trigger_chain.py — ce fichier couvre MANUAL, SCHEDULED, CATCHUP, RESUME et
l'absence d'origine.
"""

from datetime import datetime

import core.steps as steps_module
from core.pipeline import run_pipeline
from core.steps.base import BaseStep, StepResult
from database import db_manager as db


class _FakeStep(BaseStep):
    def run(self, ctx, cancel_event=None, on_progress=None) -> StepResult:
        return StepResult(success=True)


def _pipeline(name="origin-test"):
    p = db.create_pipeline(name=name)
    db.save_steps(p.id, [{"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}}])
    return p


def test_run_without_an_explicit_origin_is_null(test_db, monkeypatch):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeStep)
    p = _pipeline()

    result = run_pipeline(p.id)

    run = db.get_run(result.run_id)
    assert run.trigger_origin is None


def test_run_with_origin_manual_is_persisted(test_db, monkeypatch):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeStep)
    p = _pipeline()

    result = run_pipeline(p.id, origin="MANUAL")

    run = db.get_run(result.run_id)
    assert run.trigger_origin == "MANUAL"


def test_scheduled_run_via_the_scheduler_wrapper_is_persisted(test_db, monkeypatch):
    """core/scheduler.py::_run_scheduled_pipeline — le vrai appelant du cas SCHEDULED."""
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeStep)
    p = _pipeline()

    from core.scheduler import PipelineScheduler
    sched = PipelineScheduler()
    sched._run_scheduled_pipeline(p.id)

    run = db.get_runs(p.id, limit=1)[0]
    assert run.trigger_origin == "SCHEDULED"
    assert run.scheduled_for is not None


def test_catchup_run_carries_the_expected_scheduled_for(test_db, monkeypatch):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeStep)
    p = _pipeline()

    result = run_pipeline(p.id, origin="CATCHUP", scheduled_for=datetime(2026, 8, 25, 6, 0))

    run = db.get_run(result.run_id)
    assert run.trigger_origin == "CATCHUP"
    assert run.scheduled_for == datetime(2026, 8, 25, 6, 0)


def test_resume_overrides_whatever_origin_is_passed(test_db, monkeypatch):
    """run_pipeline() dérive toujours "RESUME" de resume_from_run_id — jamais la valeur
    d'origin passée par l'appelant dans ce cas précis (voir docstring de run_pipeline()). Même
    patron de pipeline à 2 étapes (une réussie, une qui échoue puis réussit) que
    tests/test_pipeline_run_steps.py::test_resume_marks_the_reused_step_as_skipped_resume, pour
    obtenir un vrai état de reprise persisté (resumable_state_json)."""
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeStep)

    class _SucceedsOnSecondCall(BaseStep):
        attempt = 0

        def run(self, ctx, cancel_event=None, on_progress=None):
            _SucceedsOnSecondCall.attempt += 1
            if _SucceedsOnSecondCall.attempt < 2:
                return StepResult(success=False, error="échec simulé (1re tentative)")
            return StepResult(success=True)

    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _SucceedsOnSecondCall)

    p = db.create_pipeline(name="origin-resume")
    db.save_steps(p.id, [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD", "config": {"_step_key": "fail"}},
    ])

    first = run_pipeline(p.id, origin="MANUAL")
    assert not first.success

    resumable = db.get_last_resumable_run(p.id)
    assert resumable is not None
    second = run_pipeline(p.id, origin="SCHEDULED", resume_from_run_id=resumable.id)
    assert second.success, second.error

    run = db.get_run(second.run_id)
    assert run.trigger_origin == "RESUME"
