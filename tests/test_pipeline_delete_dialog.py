"""
DataScheduler — tests/test_pipeline_delete_dialog.py
Refonte, lot A-Pipelines : A13 (fenêtre de suppression modale, remplace le QMessageBox.question
inline de PipelinesView._on_delete_pipeline).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_dialog_shows_dependents_with_their_own_schedule(qapp, test_db):
    from ui.dialogs import PipelineDeleteDialog

    a = db.create_pipeline(name="parent-dialog-test", frequency="DAILY", scheduled_time="06:00")
    b = db.create_pipeline(name="child-dialog-test", frequency="DAILY", scheduled_time="06:00")
    db.set_pipeline_trigger(b.id, a.id, "SUCCESS")

    dependents = db.get_pipelines_triggered_by(a.id)
    dlg = PipelineDeleteDialog(None, a, dependents, db.count_runs(a.id))
    text = " ".join(lbl.text() for lbl in dlg.findChildren(QLabel))

    assert "child-dialog-test" in text
    assert "garde Quotidien 06:00" in text
    # P4 (DECISIONS.md) : sans B3, un enfant a toujours sa propre planification réelle, jamais
    # le texte "n'a pas d'autre planification" de la maquette (dépend d'une colonne absente).
    assert "n'a pas d'autre planification" not in text


def test_dialog_without_dependents_shows_no_dependents_block(qapp, test_db):
    from ui.dialogs import PipelineDeleteDialog

    p = db.create_pipeline(name="no-dependents-test")
    dlg = PipelineDeleteDialog(None, p, [], 0)
    text = " ".join(lbl.text() for lbl in dlg.findChildren(QLabel))

    assert "se lance" not in text


def test_dialog_history_text_says_will_be_deleted_not_kept(qapp, test_db):
    """DECISIONS.md::P4 : garder le comportement (cascade delete), corriger le texte — jamais
    « sont conservées » (faux, Pipeline.runs a cascade="all, delete-orphan")."""
    from ui.dialogs import PipelineDeleteDialog

    p = db.create_pipeline(name="history-text-test")
    for _ in range(3):
        run = db.create_run(p.id)
        db.finish_run(run.id, "SUCCESS")

    dlg = PipelineDeleteDialog(None, p, [], db.count_runs(p.id))
    text = " ".join(lbl.text() for lbl in dlg.findChildren(QLabel))

    assert "Les 3 exécutions de l'historique seront supprimées" in text
    assert "conservées" not in text


def test_dialog_delete_button_is_danger_styled(qapp, test_db):
    from ui.dialogs import PipelineDeleteDialog

    p = db.create_pipeline(name="danger-style-test")
    dlg = PipelineDeleteDialog(None, p, [], 0)

    assert dlg.btn_delete.objectName() == "danger"


def test_export_first_button_opens_export_dialog_without_closing(qapp, test_db, monkeypatch):
    from ui.dialogs import PipelineDeleteDialog
    from ui.dialogs.pipeline_export_dialog import PipelineExportDialog

    p = db.create_pipeline(name="export-first-test")
    dlg = PipelineDeleteDialog(None, p, [], 0)

    opened = []
    monkeypatch.setattr(PipelineExportDialog, "exec", lambda self: opened.append(True))

    dlg._on_export_first()

    assert opened == [True]
    assert dlg.result() == 0   # ni accepté ni refusé — la fenêtre reste ouverte


def test_on_delete_pipeline_deletes_only_when_accepted(qapp, test_db, monkeypatch):
    from ui.dialogs import PipelineDeleteDialog
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="accept-delete-test")
    view = PipelinesView()

    monkeypatch.setattr(PipelineDeleteDialog, "exec", lambda self: QDialog.Accepted)
    view._on_delete_pipeline(p.id)

    assert db.get_pipeline(p.id) is None


def test_on_delete_pipeline_keeps_pipeline_when_rejected(qapp, test_db, monkeypatch):
    from ui.dialogs import PipelineDeleteDialog
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="reject-delete-test")
    view = PipelinesView()

    monkeypatch.setattr(PipelineDeleteDialog, "exec", lambda self: QDialog.Rejected)
    view._on_delete_pipeline(p.id)

    assert db.get_pipeline(p.id) is not None
