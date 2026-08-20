"""
DataScheduler — tests/test_cooperative_cancellation.py
Vérifie que core/pipeline.py distingue bien une étape qui a coopéré à l'annulation (retourne un
échec ordinaire APRÈS avoir positionné cancel_event) d'un vrai échec — même patron de steps
factices substitués dans le registre que tests/test_pipeline_graph_engine.py, mais focalisé sur
_execute_linear()/_execute_graph()/_run_step_with_policy() plutôt que sur le moteur DAG lui-même.
"""

from types import SimpleNamespace

import core.pipeline as pipeline_module
import core.steps as steps_module
from core.pipeline import _run_step_with_policy, PipelineResult, run_pipeline
from core.steps.base import BaseStep, StepContext, StepResult
from database import db_manager as db


def _edge(from_key, to_key, from_port="output_file", to_port="input"):
    return {"from_step_key": from_key, "from_port": from_port, "to_step_key": to_key, "to_port": to_port}


class _FakeCancellingStep(BaseStep):
    """Simule une étape qui a un vrai point d'interruption (comme PythonScriptStep/SqlExporter) :
    positionne cancel_event elle-même — exactement ce qu'un vrai run_pipeline() ferait via
    request_cancel() depuis un autre thread pendant que cette étape tourne — puis retourne un
    échec ordinaire, comme le font PythonScriptStep/SqlExporter/SqlLoader/etc. une fois annulés."""

    def run(self, ctx, cancel_event=None, on_progress=None) -> StepResult:
        if cancel_event is not None:
            cancel_event.set()
        return StepResult(success=False, error="peu importe — coopération à l'annulation")


class _FakeNeverRunStep(BaseStep):
    def run(self, ctx, cancel_event=None, on_progress=None) -> StepResult:
        raise AssertionError("ne doit jamais s'exécuter après une annulation détectée en amont")


def _status_str(val) -> str:
    return val.value if hasattr(val, "value") else str(val)


def test_run_pipeline_linear_reports_cancelled_not_failed_when_a_step_cooperates(test_db, monkeypatch):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeCancellingStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeNeverRunStep)

    pipeline = db.create_pipeline(name="linear-cancel-test")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {}},
        {"step_type": "LOCAL_COPY", "config": {}},
    ])

    result = run_pipeline(pipeline.id)

    assert not result.success
    assert "interrompue par l'utilisateur" in result.error
    run = db.get_run(result.run_id)
    assert _status_str(run.status) == "CANCELLED"
    pipeline_row = db.get_pipeline(pipeline.id)
    assert _status_str(pipeline_row.last_status) == "CANCELLED"


def test_run_pipeline_graph_reports_cancelled_not_failed_when_a_step_cooperates(test_db, monkeypatch):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeCancellingStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeNeverRunStep)

    pipeline = db.create_pipeline(name="graph-cancel-test")
    steps = [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
    ]
    db.save_pipeline_graph(pipeline.id, steps, edges=[_edge("a", "b")])

    result = run_pipeline(pipeline.id)

    assert not result.success
    assert "interrompue par l'utilisateur" in result.error
    run = db.get_run(result.run_id)
    assert _status_str(run.status) == "CANCELLED"


def test_run_step_with_policy_never_retries_a_cancelled_step(monkeypatch):
    """Retenter une étape que l'utilisateur vient d'annuler serait activement contraire à sa
    demande — contrairement à un vrai échec (retry_count > 0 s'applique normalement), une
    coopération à l'annulation doit court-circuiter la boucle de relance immédiatement."""
    import threading
    monkeypatch.setattr(pipeline_module, "RETRY_DELAY_S", 0)

    call_count = {"n": 0}

    class _CancellingStep:
        def run(self, ctx, cancel_event=None, on_progress=None):
            call_count["n"] += 1
            if cancel_event is not None:
                cancel_event.set()
            return StepResult(success=False, error="annulé")

    fake_step = SimpleNamespace(retry_count=3, timeout_s=0)
    cancel_event = threading.Event()
    ctx = StepContext()
    result = PipelineResult()

    step_result = _run_step_with_policy(
        _CancellingStep(), ctx, fake_step, lambda *a: None, result, cancel_event,
    )

    assert not step_result.success
    assert call_count["n"] == 1   # jamais retenté malgré retry_count=3


def test_run_step_with_policy_still_retries_a_genuine_failure(monkeypatch):
    """Non-régression : un vrai échec (cancel_event jamais positionné) continue de suivre la
    politique de relance normale, inchangée par ce chantier."""
    monkeypatch.setattr(pipeline_module, "RETRY_DELAY_S", 0)
    call_count = {"n": 0}

    class _FailingStep:
        def run(self, ctx, cancel_event=None, on_progress=None):
            call_count["n"] += 1
            return StepResult(success=False, error="échec réseau transitoire")

    fake_step = SimpleNamespace(retry_count=2, timeout_s=0)
    ctx = StepContext()
    result = PipelineResult()

    step_result = _run_step_with_policy(
        _FailingStep(), ctx, fake_step, lambda *a: None, result, cancel_event=None,
    )

    assert not step_result.success
    assert call_count["n"] == 3   # 1 tentative initiale + 2 relances
