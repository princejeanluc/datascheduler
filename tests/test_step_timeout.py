"""
DataScheduler — tests/test_step_timeout.py
Vérifie le timeout par étape (chantier J.1) : _run_step_with_policy() en isolation (délai
dépassé → échec propre, délai respecté → succès normal, timeout_s=0 → jamais de timeout, un
timeout compte comme un échec pour retry_count), puis bout en bout via run_pipeline().
"""

import time
from types import SimpleNamespace

from core.pipeline import _run_step_with_policy, PipelineResult, run_pipeline
from core.steps.base import BaseStep, StepContext, StepResult
import core.steps as steps_module
from database import db_manager as db


def _fake_step(retry_count=0, timeout_s=0, run_always=False, retry_interval_s=0):
    return SimpleNamespace(retry_count=retry_count, timeout_s=timeout_s, run_always=run_always,
                            retry_interval_s=retry_interval_s)


class _SleepyStep(BaseStep):
    def __init__(self, config):
        super().__init__(config)
        self.calls = 0

    def run(self, ctx, cancel_event=None, on_progress=None):
        self.calls += 1
        time.sleep(self.config.get("sleep_s", 0))
        return StepResult(success=True)


def test_step_within_timeout_succeeds_normally():
    executor = _SleepyStep({"sleep_s": 0})
    result = PipelineResult()
    ctx = StepContext()
    step_result = _run_step_with_policy(executor, ctx, _fake_step(timeout_s=5), lambda *a: None, result)

    assert step_result.success


def test_step_exceeding_timeout_fails_cleanly():
    executor = _SleepyStep({"sleep_s": 0.3})
    result = PipelineResult()
    ctx = StepContext()
    step_result = _run_step_with_policy(executor, ctx, _fake_step(timeout_s=0.1), lambda *a: None, result)

    assert not step_result.success
    assert "Délai dépassé" in step_result.error


def test_timeout_zero_never_triggers_even_for_a_slow_step():
    executor = _SleepyStep({"sleep_s": 0.2})
    result = PipelineResult()
    ctx = StepContext()
    step_result = _run_step_with_policy(executor, ctx, _fake_step(timeout_s=0), lambda *a: None, result)

    assert step_result.success


def test_timeout_counts_as_a_failure_for_retry_count():
    # _fake_step() a retry_interval_s=0 par défaut — évite les délais réels entre tentatives.
    executor = _SleepyStep({"sleep_s": 0.3})
    result = PipelineResult()
    ctx = StepContext()
    step_result = _run_step_with_policy(
        executor, ctx, _fake_step(timeout_s=0.05, retry_count=2), lambda *a: None, result,
    )

    assert not step_result.success
    # 1 tentative initiale + 2 relances = 3 appels au step, chacun démarrant un nouveau
    # thread-traînard indépendant (accepté — voir docstring de _run_step_with_policy).
    assert executor.calls == 3


def test_run_pipeline_continues_after_a_step_timeout(test_db, monkeypatch):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _SleepyStep)

    pipeline = db.create_pipeline(name="test-timeout")
    # timeout_s est un entier (colonne DB, secondes entières) — contrairement aux tests ci-dessus
    # qui testent _run_step_with_policy() directement avec des valeurs fractionnaires pour rester
    # rapides sans passer par la DB.
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"sleep_s": 1.3}, "timeout_s": 1},
        {"step_type": "DB_EXTRACT", "config": {"sleep_s": 0}, "run_always": True},
    ])

    result = run_pipeline(pipeline.id)

    assert not result.success
    assert "Délai dépassé" in result.log_text
