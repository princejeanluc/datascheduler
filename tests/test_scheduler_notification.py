"""
DataScheduler — tests/test_scheduler_notification.py
Vérifie que les runs planifiés déclenchent bien on_job_success/on_job_error — même quand
run_pipeline() échoue proprement (PipelineResult(success=False)) sans lever d'exception, ce
qu'APScheduler ne peut pas détecter tout seul (EVENT_JOB_ERROR ne se déclenche que sur une
exception réelle). C'est exactement le trou trouvé : func=run_pipeline directement comme cible
de job ne notifiait jamais un échec planifié propre, seul trigger_now() (lancement manuel)
inspectait le résultat. Corrigé par PipelineScheduler._run_scheduled_pipeline().
"""

import core.pipeline as pipeline_module
from core.pipeline import PipelineResult
from core.scheduler import PipelineScheduler


def test_scheduled_failure_triggers_on_job_error(monkeypatch):
    fake_result = PipelineResult()
    fake_result.success = False
    fake_result.error = "Connexion Oracle refusée"
    monkeypatch.setattr(pipeline_module, "run_pipeline", lambda pipeline_id: fake_result)

    calls = {"success": [], "error": []}
    sched = PipelineScheduler(
        on_job_success=lambda pid, path: calls["success"].append((pid, path)),
        on_job_error=lambda pid, err: calls["error"].append((pid, err)),
    )

    sched._run_scheduled_pipeline(42)

    assert calls["error"] == [(42, "Connexion Oracle refusée")]
    assert calls["success"] == []


def test_scheduled_success_triggers_on_job_success(monkeypatch):
    fake_result = PipelineResult()
    fake_result.success = True
    fake_result.remote_path = "/export/ventes.csv"
    monkeypatch.setattr(pipeline_module, "run_pipeline", lambda pipeline_id: fake_result)

    calls = {"success": [], "error": []}
    sched = PipelineScheduler(
        on_job_success=lambda pid, path: calls["success"].append((pid, path)),
        on_job_error=lambda pid, err: calls["error"].append((pid, err)),
    )

    sched._run_scheduled_pipeline(7)

    assert calls["success"] == [(7, "/export/ventes.csv")]
    assert calls["error"] == []


def test_no_callback_configured_does_not_raise(monkeypatch):
    fake_result = PipelineResult()
    fake_result.success = False
    fake_result.error = "peu importe"
    monkeypatch.setattr(pipeline_module, "run_pipeline", lambda pipeline_id: fake_result)

    sched = PipelineScheduler()   # ni on_job_success ni on_job_error
    sched._run_scheduled_pipeline(1)   # ne doit pas lever
