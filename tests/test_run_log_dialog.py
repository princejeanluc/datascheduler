"""
DataScheduler — tests/test_run_log_dialog.py
Vérifie que le dialogue "Voir le log complet" (chantier N) affiche le log partiel d'un run
encore RUNNING (au lieu de "(aucun log enregistré)") et se rafraîchit tant qu'il tourne, alors
qu'auparavant PipelineRun.log_text n'était écrit qu'une seule fois à la toute fin — ouvrir ce
dialogue sur un run en cours ne montrait donc jamais rien d'utile. QDialog.exec() est
monkeypatché pour éviter la boucle modale (même patron que test_pipeline_detail_dialog.py).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QTextEdit

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


def test_shows_partial_log_and_polls_while_run_is_still_running(qapp, test_db, monkeypatch):
    from ui.main_window.run_log_dialog import open_run_log_dialog

    pipeline = db.create_pipeline(name="log-dialog-running")
    run = db.create_run(pipeline.id)
    db.update_run_progress(run.id, "Étape 1/2 : Extraction", "[10:00:00] log partiel")

    captured = {}
    _capture_dialog(monkeypatch, captured)

    open_run_log_dialog(None, run.id)

    dlg = captured["dlg"]
    txt = dlg.findChild(QTextEdit)
    assert "log partiel" in txt.toPlainText()
    assert "(aucun log enregistré)" not in txt.toPlainText()

    timers = dlg.findChildren(QTimer)
    assert len(timers) == 1
    assert timers[0].isActive()

    # Le run progresse pendant que le dialogue reste ouvert — simule un tick du timer.
    db.update_run_progress(
        run.id, "Étape 2/2 : Envoi",
        "[10:00:00] log partiel\n[10:00:05] envoi en cours",
    )
    timers[0].timeout.emit()

    assert "envoi en cours" in txt.toPlainText()


def test_stops_polling_once_the_run_reaches_a_terminal_status(qapp, test_db, monkeypatch):
    from ui.main_window.run_log_dialog import open_run_log_dialog

    pipeline = db.create_pipeline(name="log-dialog-finishes")
    run = db.create_run(pipeline.id)
    db.update_run_progress(run.id, "Étape 1/1 : Export", "[10:00:00] en cours")

    captured = {}
    _capture_dialog(monkeypatch, captured)
    open_run_log_dialog(None, run.id)
    dlg = captured["dlg"]
    timer = dlg.findChildren(QTimer)[0]
    assert timer.isActive()

    db.finish_run(run.id, status="SUCCESS", log_text="[10:00:00] en cours\n[10:00:02] terminé")
    timer.timeout.emit()

    assert not timer.isActive()
    txt = dlg.findChild(QTextEdit)
    assert "terminé" in txt.toPlainText()


def test_no_polling_when_run_is_already_finished_at_open_time(qapp, test_db, monkeypatch):
    from ui.main_window.run_log_dialog import open_run_log_dialog

    pipeline = db.create_pipeline(name="log-dialog-already-done")
    run = db.create_run(pipeline.id)
    db.finish_run(run.id, status="SUCCESS", log_text="log complet")

    captured = {}
    _capture_dialog(monkeypatch, captured)
    open_run_log_dialog(None, run.id)
    dlg = captured["dlg"]

    assert dlg.findChildren(QTimer) == []
    txt = dlg.findChild(QTextEdit)
    assert txt.toPlainText() == "log complet"
