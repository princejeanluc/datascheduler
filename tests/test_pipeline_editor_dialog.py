"""
DataScheduler — tests/test_pipeline_editor_dialog.py
Fumée : PipelineEditorDialog s'ouvre sans erreur (offscreen Qt, même réflexe que
tests/test_export_dialog.py) — vérifie en particulier la confirmation à la suppression d'une
étape, ajoutée pour éviter qu'un clic malheureux supprime une étape sans retour arrière possible
(persona "Amélie", étude UX).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from ui.step_editor import PipelineEditorDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _dialog_with_one_step(qapp, test_db):
    dlg = PipelineEditorDialog(None)
    dlg._steps_data = [
        {"step_type": "DB_EXTRACT", "label": "Ma source", "config": {}, "retry_count": 0, "run_always": False},
    ]
    return dlg


def test_delete_step_asks_for_confirmation(qapp, test_db, monkeypatch):
    dlg = _dialog_with_one_step(qapp, test_db)

    asked = {}
    def fake_question(*args, **kwargs):
        asked["called"] = True
        return QMessageBox.No
    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))

    dlg._delete_step(0)

    assert asked.get("called")
    assert len(dlg._steps_data) == 1   # refusé -> rien supprimé


def test_delete_step_proceeds_when_confirmed(qapp, test_db, monkeypatch):
    dlg = _dialog_with_one_step(qapp, test_db)

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    dlg._delete_step(0)

    assert dlg._steps_data == []


def test_delete_step_confirmation_message_names_the_step(qapp, test_db, monkeypatch):
    dlg = _dialog_with_one_step(qapp, test_db)

    captured = {}
    def fake_question(parent, title, text, *a, **k):
        captured["text"] = text
        return QMessageBox.No
    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))

    dlg._delete_step(0)

    assert "Ma source" in captured["text"]
