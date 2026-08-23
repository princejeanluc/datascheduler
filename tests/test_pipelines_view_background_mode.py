"""
DataScheduler — tests/test_pipelines_view_background_mode.py
Chantier exécution en arrière-plan : _on_run_pipeline()/_schedule_if_possible() de PipelinesView
doivent déléguer au worker (core/execution_mode.py) plutôt que d'appeler le scheduler local ou
RunProgressDialog directement dès que AppSettings.execution_mode == "BACKGROUND" — et rester
inchangés en mode IN_APP (couvert ailleurs, notamment test_pipelines_view_action_menu.py).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_on_run_pipeline_delegates_to_worker_and_opens_remote_dialog(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    db.update_app_settings(execution_mode="BACKGROUND")
    p = db.create_pipeline(name="run-background-test")
    # Étape valide (chantier UX éditeur, Lot 1) — _on_run_pipeline() valide désormais la
    # structure du pipeline avant de lancer ; un pipeline sans étape déclencherait une vraie
    # boîte de dialogue bloquante, hors du périmètre de ce test (dispatch background/in-app).
    db.save_steps(p.id, [{"step_type": "DB_EXTRACT", "config": {}}])
    view = PipelinesView()

    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.Accepted)
    remote_calls = []
    monkeypatch.setattr(
        "ui.main_window.remote_run_dialog.open_remote_run_dialog",
        lambda parent, pid, name: remote_calls.append((pid, name)),
    )

    view._on_run_pipeline(p.id)

    assert remote_calls == [(p.id, p.name)]
    pending = db.get_pending_worker_commands()
    assert any(c.command == "RUN_NOW" for c in pending)


def test_on_run_pipeline_stays_local_in_app_mode(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="run-local-test")
    db.save_steps(p.id, [{"step_type": "DB_EXTRACT", "config": {}}])
    view = PipelinesView()

    exec_calls = []
    monkeypatch.setattr(QDialog, "exec", lambda self: exec_calls.append(True) or QDialog.Accepted)
    remote_calls = []
    monkeypatch.setattr(
        "ui.main_window.remote_run_dialog.open_remote_run_dialog",
        lambda parent, pid, name: remote_calls.append((pid, name)),
    )

    view._on_run_pipeline(p.id)

    assert remote_calls == []
    assert exec_calls == [True]   # RunProgressDialog().exec() appelé localement
    assert db.get_pending_worker_commands() == []


def test_on_run_pipeline_uses_db_status_for_overlap_check_in_background_mode(qapp, test_db, monkeypatch):
    """is_pipeline_running() (mémoire, process desktop) resterait toujours False en mode
    arrière-plan même si le worker exécute réellement le pipeline — la pré-vérification
    "déjà en cours" doit donc s'appuyer sur Pipeline.last_status (base), pas sur l'état local."""
    from PySide6.QtWidgets import QMessageBox
    from database.models import Pipeline, PipelineStatus
    from ui.main_window.pipelines_view import PipelinesView

    db.update_app_settings(execution_mode="BACKGROUND")
    p = db.create_pipeline(name="run-overlap-test", prevent_overlap=True)
    with db.get_session() as s:
        obj = s.get(Pipeline, p.id)
        obj.last_status = PipelineStatus.RUNNING

    view = PipelinesView()

    box_calls = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: box_calls.append(True))
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: None)

    view._on_run_pipeline(p.id)

    assert box_calls == [True]   # la boîte "déjà en cours" a bien été déclenchée


def test_schedule_if_possible_delegates_reload_in_background_mode(test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    db.update_app_settings(execution_mode="BACKGROUND")
    p = db.create_pipeline(name="schedule-background-test")

    PipelinesView._schedule_if_possible(p.id)

    pending = db.get_pending_worker_commands()
    assert any(c.command == "RELOAD" for c in pending)


def test_schedule_if_possible_stays_local_in_app_mode(test_db):
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="schedule-local-test")

    PipelinesView._schedule_if_possible(p.id)   # ne doit pas lever (RuntimeError capturée)

    assert db.get_pending_worker_commands() == []
