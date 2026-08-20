"""
DataScheduler — tests/test_pipeline_trigger_chain.py
Vérifie le déclenchement conditionnel entre pipelines (chantier P) :
core.pipeline._trigger_downstream_pipelines() — appelée par run_pipeline() à la fin d'un run
(sauf annulation) — et son intégration de bout en bout. Le scheduler réel (core.scheduler) est
monkeypatché : on capture les appels à trigger_now() plutôt que de vraiment lancer un thread/
run_pipeline() imbriqué.
"""

import core.pipeline as pipeline_module
import core.scheduler as scheduler_module
from core.pipeline import run_pipeline
from core.steps.base import BaseStep, StepResult
from database import db_manager as db


class _FakeScheduler:
    def __init__(self, raise_runtime_error=False):
        self.triggered: list[int] = []
        self._raise_runtime_error = raise_runtime_error

    def trigger_now(self, pipeline_id):
        if self._raise_runtime_error:
            raise RuntimeError("Scheduler non initialisé.")
        self.triggered.append(pipeline_id)
        return True


def _install_fake_scheduler(monkeypatch, **kwargs):
    fake = _FakeScheduler(**kwargs)
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: fake)
    return fake


# ──────────────────────────────────────────────
#  _trigger_downstream_pipelines() — unitaire
# ──────────────────────────────────────────────

def test_success_fires_success_and_always_children_not_failure(test_db, monkeypatch):
    a = db.create_pipeline(name="A")
    b_success = db.create_pipeline(name="B_SUCCESS")
    b_always  = db.create_pipeline(name="B_ALWAYS")
    b_failure = db.create_pipeline(name="B_FAILURE")
    db.set_pipeline_trigger(b_success.id, a.id, "SUCCESS")
    db.set_pipeline_trigger(b_always.id,  a.id, "ALWAYS")
    db.set_pipeline_trigger(b_failure.id, a.id, "FAILURE")

    fake = _install_fake_scheduler(monkeypatch)
    pipeline_module._trigger_downstream_pipelines(a.id, "SUCCESS")

    assert set(fake.triggered) == {b_success.id, b_always.id}


def test_failed_fires_failure_and_always_children_not_success(test_db, monkeypatch):
    a = db.create_pipeline(name="A")
    b_success = db.create_pipeline(name="B_SUCCESS")
    b_always  = db.create_pipeline(name="B_ALWAYS")
    b_failure = db.create_pipeline(name="B_FAILURE")
    db.set_pipeline_trigger(b_success.id, a.id, "SUCCESS")
    db.set_pipeline_trigger(b_always.id,  a.id, "ALWAYS")
    db.set_pipeline_trigger(b_failure.id, a.id, "FAILURE")

    fake = _install_fake_scheduler(monkeypatch)
    pipeline_module._trigger_downstream_pipelines(a.id, "FAILED")

    assert set(fake.triggered) == {b_failure.id, b_always.id}


def test_cancelled_status_never_fires_anything_even_if_called_directly(test_db, monkeypatch):
    """Défense en profondeur : run_pipeline() n'appelle jamais cette fonction pour un run
    CANCELLED, mais même appelée directement avec ce statut, aucune condition ne doit matcher."""
    a = db.create_pipeline(name="A")
    b = db.create_pipeline(name="B")
    db.set_pipeline_trigger(b.id, a.id, "ALWAYS")

    fake = _install_fake_scheduler(monkeypatch)
    pipeline_module._trigger_downstream_pipelines(a.id, "CANCELLED")

    assert fake.triggered == []


def test_inactive_child_is_skipped(test_db, monkeypatch):
    a = db.create_pipeline(name="A")
    b = db.create_pipeline(name="B")
    db.set_pipeline_trigger(b.id, a.id, "SUCCESS")
    db.set_pipeline_active(b.id, False)

    fake = _install_fake_scheduler(monkeypatch)
    pipeline_module._trigger_downstream_pipelines(a.id, "SUCCESS")

    assert fake.triggered == []


def test_runtime_error_from_uninitialized_scheduler_is_swallowed(test_db, monkeypatch):
    a = db.create_pipeline(name="A")
    b = db.create_pipeline(name="B")
    db.set_pipeline_trigger(b.id, a.id, "SUCCESS")

    _install_fake_scheduler(monkeypatch, raise_runtime_error=True)

    pipeline_module._trigger_downstream_pipelines(a.id, "SUCCESS")   # ne doit pas lever


def test_unexpected_internal_exception_never_propagates(test_db, monkeypatch):
    def _boom(parent_pipeline_id):
        raise RuntimeError("panne inattendue")

    monkeypatch.setattr(db, "get_pipelines_triggered_by", _boom)
    pipeline_module._trigger_downstream_pipelines(999, "SUCCESS")   # ne doit pas lever


def test_pipeline_with_no_children_is_a_silent_noop(test_db, monkeypatch):
    a = db.create_pipeline(name="A")
    fake = _install_fake_scheduler(monkeypatch)
    pipeline_module._trigger_downstream_pipelines(a.id, "SUCCESS")
    assert fake.triggered == []


# ──────────────────────────────────────────────
#  Intégration via run_pipeline()
# ──────────────────────────────────────────────

class _SucceedingStep(BaseStep):
    def run(self, ctx, cancel_event=None, on_progress=None):
        return StepResult(success=True)


class _FailingStep(BaseStep):
    def run(self, ctx, cancel_event=None, on_progress=None):
        return StepResult(success=False, error="échec simulé")


def test_run_pipeline_triggers_downstream_pipeline_on_success(test_db, monkeypatch):
    import core.steps as steps_module
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _SucceedingStep)

    a = db.create_pipeline(name="A")
    db.save_steps(a.id, [{"step_type": "DB_EXTRACT", "config": {}}])
    b = db.create_pipeline(name="B")
    db.set_pipeline_trigger(b.id, a.id, "SUCCESS")

    fake = _install_fake_scheduler(monkeypatch)
    result = run_pipeline(a.id)

    assert result.success
    assert fake.triggered == [b.id]


def test_run_pipeline_triggers_downstream_pipeline_on_failure(test_db, monkeypatch):
    import core.steps as steps_module
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FailingStep)

    a = db.create_pipeline(name="A")
    db.save_steps(a.id, [{"step_type": "DB_EXTRACT", "config": {}}])
    b = db.create_pipeline(name="B")
    db.set_pipeline_trigger(b.id, a.id, "FAILURE")

    fake = _install_fake_scheduler(monkeypatch)
    result = run_pipeline(a.id)

    assert not result.success
    assert fake.triggered == [b.id]


def test_run_pipeline_does_not_trigger_success_child_on_failure(test_db, monkeypatch):
    import core.steps as steps_module
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FailingStep)

    a = db.create_pipeline(name="A")
    db.save_steps(a.id, [{"step_type": "DB_EXTRACT", "config": {}}])
    b = db.create_pipeline(name="B")
    db.set_pipeline_trigger(b.id, a.id, "SUCCESS")

    fake = _install_fake_scheduler(monkeypatch)
    run_pipeline(a.id)

    assert fake.triggered == []
