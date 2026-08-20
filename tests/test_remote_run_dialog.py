"""
DataScheduler — tests/test_remote_run_dialog.py
Chantier exécution en arrière-plan : ui/main_window/remote_run_dialog.py suit un run délégué au
worker — avant l'apparition du run en base (poll "en attente"), puis en relisant
PipelineRun.log_text/current_step_label une fois trouvé, même mécanisme incrémental que
run_log_dialog.py (tests/test_run_log_dialog.py), juste un point d'entrée différent (le run_id
n'est pas connu à l'ouverture). QDialog.exec() monkeypatché pour éviter la boucle modale, même
patron que test_run_log_dialog.py.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QTextEdit, QPushButton

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _capture_dialog(monkeypatch, captured):
    def _fake_exec(self):
        captured["dlg"] = self
        return QDialog.Accepted
    monkeypatch.setattr(QDialog, "exec", _fake_exec)


def _button(dlg, text):
    return next(b for b in dlg.findChildren(QPushButton) if b.text() == text)


def _active_steps_label(dlg):
    # Ordre de construction dans open_remote_run_dialog() : lbl_title, lbl_step,
    # lbl_active_steps, lbl_err — le 3e QLabel créé.
    return dlg.findChildren(QLabel)[2]


def test_waits_for_run_to_appear_before_showing_log(qapp, test_db, monkeypatch):
    from ui.main_window.remote_run_dialog import open_remote_run_dialog

    pipeline = db.create_pipeline(name="remote-run-pending")

    captured = {}
    _capture_dialog(monkeypatch, captured)
    open_remote_run_dialog(None, pipeline.id, pipeline.name)

    dlg = captured["dlg"]
    timer = dlg.findChildren(QTimer)[0]
    assert timer.isActive()
    txt = dlg.findChild(QTextEdit)
    assert "attente" in txt.toPlainText().lower()

    # Le worker ramasse la commande et crée le run — simule un tick du timer.
    run = db.create_run(pipeline.id)
    db.update_run_progress(run.id, "Étape 1/1", "[10:00:00] démarré")
    timer.timeout.emit()

    assert "démarré" in txt.toPlainText()


def test_switches_to_live_log_once_run_found_and_polls_updates(qapp, test_db, monkeypatch):
    from ui.main_window.remote_run_dialog import open_remote_run_dialog

    pipeline = db.create_pipeline(name="remote-run-live")

    captured = {}
    _capture_dialog(monkeypatch, captured)
    open_remote_run_dialog(None, pipeline.id, pipeline.name)
    dlg = captured["dlg"]
    timer = dlg.findChildren(QTimer)[0]

    # Le worker ramasse la commande APRÈS l'ouverture du dialogue (started_at postérieur à
    # enqueued_at, capturé à l'ouverture) — sinon _tick() l'ignorerait comme un run antérieur.
    run = db.create_run(pipeline.id)
    db.update_run_progress(run.id, "Étape 1/2", "[10:00:00] en cours")
    timer.timeout.emit()
    txt = dlg.findChild(QTextEdit)
    assert "en cours" in txt.toPlainText()

    db.update_run_progress(run.id, "Étape 2/2", "[10:00:00] en cours\n[10:00:05] presque fini")
    timer.timeout.emit()
    assert "presque fini" in txt.toPlainText()


def test_stops_polling_once_run_reaches_terminal_status(qapp, test_db, monkeypatch):
    from ui.main_window.remote_run_dialog import open_remote_run_dialog

    pipeline = db.create_pipeline(name="remote-run-finishes")

    captured = {}
    _capture_dialog(monkeypatch, captured)
    open_remote_run_dialog(None, pipeline.id, pipeline.name)
    dlg = captured["dlg"]
    timer = dlg.findChildren(QTimer)[0]

    run = db.create_run(pipeline.id)
    db.update_run_progress(run.id, "Étape 1/1", "[10:00:00] en cours")
    timer.timeout.emit()   # bascule sur le run trouvé

    db.finish_run(run.id, status="SUCCESS", log_text="[10:00:00] en cours\n[10:00:02] terminé")
    timer.timeout.emit()

    assert not timer.isActive()
    txt = dlg.findChild(QTextEdit)
    assert "terminé" in txt.toPlainText()


def test_stop_button_delegates_cancel_to_worker(qapp, test_db, monkeypatch):
    from ui.main_window.remote_run_dialog import open_remote_run_dialog

    db.update_app_settings(execution_mode="BACKGROUND")
    pipeline = db.create_pipeline(name="remote-run-stop")

    captured = {}
    _capture_dialog(monkeypatch, captured)
    open_remote_run_dialog(None, pipeline.id, pipeline.name)
    dlg = captured["dlg"]

    _button(dlg, "Arrêter").click()

    pending = db.get_pending_worker_commands()
    assert any(c.command == "CANCEL" for c in pending)


# ──────────────────────────────────────────────
#  Étapes actives en parallèle (chantier parallélisme intra-pipeline)
# ──────────────────────────────────────────────

def test_shows_nothing_when_at_most_one_step_is_active(qapp, test_db, monkeypatch):
    from ui.main_window.remote_run_dialog import open_remote_run_dialog

    pipeline = db.create_pipeline(name="remote-run-single-active")
    captured = {}
    _capture_dialog(monkeypatch, captured)
    open_remote_run_dialog(None, pipeline.id, pipeline.name)
    dlg = captured["dlg"]
    timer = dlg.findChildren(QTimer)[0]

    run = db.create_run(pipeline.id)
    db.update_run_active_steps(run.id, {"a": {"label": "Étape A", "pct": 40}})
    timer.timeout.emit()

    assert _active_steps_label(dlg).isHidden()


def test_shows_list_when_multiple_steps_active(qapp, test_db, monkeypatch):
    from ui.main_window.remote_run_dialog import open_remote_run_dialog

    pipeline = db.create_pipeline(name="remote-run-multi-active")
    captured = {}
    _capture_dialog(monkeypatch, captured)
    open_remote_run_dialog(None, pipeline.id, pipeline.name)
    dlg = captured["dlg"]
    timer = dlg.findChildren(QTimer)[0]

    run = db.create_run(pipeline.id)
    db.update_run_active_steps(run.id, {
        "a": {"label": "Étape A", "pct": 40}, "b": {"label": "Étape B", "pct": 10},
    })
    timer.timeout.emit()

    lbl = _active_steps_label(dlg)
    assert not lbl.isHidden()
    assert "Étape A" in lbl.text()
    assert "Étape B" in lbl.text()
