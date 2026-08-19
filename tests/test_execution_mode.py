"""
DataScheduler — tests/test_execution_mode.py
Chantier exécution en arrière-plan : core/execution_mode.py est le point de décision unique
"cette action doit-elle s'exécuter localement, ou être déléguée au worker ?" — verrouille le
contrat de retour (True = délégué, l'appelant ne fait rien localement) selon AppSettings.
execution_mode, et le format des commandes déposées dans la file.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from database import db_manager as db
from core.execution_mode import (
    is_background_mode_active,
    request_run_now,
    request_reload,
    request_cancel_run,
    is_pipeline_running_anywhere,
)


def test_is_background_mode_active_reflects_app_settings(test_db):
    assert is_background_mode_active() is False
    db.update_app_settings(execution_mode="BACKGROUND")
    assert is_background_mode_active() is True


def test_request_run_now_returns_false_and_enqueues_nothing_in_app_mode(test_db):
    assert request_run_now(5) is False
    assert db.get_pending_worker_commands() == []


def test_request_run_now_delegates_and_enqueues_in_background_mode(test_db):
    db.update_app_settings(execution_mode="BACKGROUND")

    assert request_run_now(5) is True

    pending = db.get_pending_worker_commands()
    assert len(pending) == 1
    assert pending[0].command == "RUN_NOW"
    assert pending[0].payload_json == '{"pipeline_id": 5}'


def test_request_reload_returns_false_in_app_mode(test_db):
    assert request_reload() is False
    assert db.get_pending_worker_commands() == []


def test_request_reload_delegates_in_background_mode(test_db):
    db.update_app_settings(execution_mode="BACKGROUND")

    assert request_reload() is True

    pending = db.get_pending_worker_commands()
    assert len(pending) == 1
    assert pending[0].command == "RELOAD"
    assert pending[0].payload_json is None


def test_request_cancel_run_returns_false_in_app_mode(test_db):
    assert request_cancel_run(5) is False
    assert db.get_pending_worker_commands() == []


def test_request_cancel_run_delegates_in_background_mode(test_db):
    db.update_app_settings(execution_mode="BACKGROUND")

    assert request_cancel_run(5) is True

    pending = db.get_pending_worker_commands()
    assert len(pending) == 1
    assert pending[0].command == "CANCEL"
    assert pending[0].payload_json == '{"pipeline_id": 5}'


def test_is_pipeline_running_anywhere_reflects_db_status(test_db):
    p = db.create_pipeline(name="exec-mode-test")
    assert is_pipeline_running_anywhere(p.id) is False

    with db.get_session() as s:
        from database.models import Pipeline, PipelineStatus
        obj = s.get(Pipeline, p.id)
        obj.last_status = PipelineStatus.RUNNING

    assert is_pipeline_running_anywhere(p.id) is True


def test_is_pipeline_running_anywhere_false_for_unknown_pipeline(test_db):
    assert is_pipeline_running_anywhere(99999) is False
