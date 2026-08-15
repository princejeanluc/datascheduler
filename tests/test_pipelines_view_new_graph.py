"""
DataScheduler — tests/test_pipelines_view_new_graph.py
Fumée (offscreen Qt) : bouton "Nouveau (graphique)" de PipelinesView (chantier gouvernance/UX,
G.4) — permet de créer un pipeline directement dans l'éditeur graphique, sans passer par
l'éditeur classique qui imposait au moins une étape avant d'enregistrer (friction réelle pour
qui ne veut travailler qu'en graphe, confirmée en lisant pipeline_editor_dialog.py::_validate()).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QInputDialog

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeGraphDialog:
    last_pipeline_id = None
    accept = True

    def __init__(self, parent, pipeline):
        _FakeGraphDialog.last_pipeline_id = pipeline.id

    def exec(self):
        return QDialog.Accepted if _FakeGraphDialog.accept else QDialog.Rejected


def test_new_pipeline_graph_creates_shell_and_opens_graph_editor(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("mon-pipeline", True)))
    _FakeGraphDialog.accept = True
    monkeypatch.setattr("ui.graph_editor.PipelineGraphEditorDialog", _FakeGraphDialog)

    view = PipelinesView()
    view._on_new_pipeline_graph()

    pipelines = db.get_pipelines()
    assert len(pipelines) == 1
    assert pipelines[0].name == "mon-pipeline"
    assert _FakeGraphDialog.last_pipeline_id == pipelines[0].id
    assert len(db.get_steps(pipelines[0].id)) == 0   # pipeline vide, à remplir dans le graphe


def test_new_pipeline_graph_cancelled_name_prompt_creates_nothing(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))

    view = PipelinesView()
    view._on_new_pipeline_graph()

    assert db.get_pipelines() == []


def test_new_pipeline_graph_blank_name_creates_nothing(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("   ", True)))

    view = PipelinesView()
    view._on_new_pipeline_graph()

    assert db.get_pipelines() == []


def test_new_pipeline_graph_schedules_the_pipeline_on_accept(qapp, test_db, monkeypatch):
    """Bug réel : un pipeline créé via ce raccourci restait actif en base mais n'était jamais
    enregistré auprès d'APScheduler avant le prochain redémarrage de l'app."""
    from ui.main_window.pipelines_view import PipelinesView

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("scheduled-shell", True)))
    _FakeGraphDialog.accept = True
    monkeypatch.setattr("ui.graph_editor.PipelineGraphEditorDialog", _FakeGraphDialog)

    calls = []
    view = PipelinesView()
    monkeypatch.setattr(view, "_schedule_if_possible", lambda pid: calls.append(pid))
    view._on_new_pipeline_graph()

    p = next(p for p in db.get_pipelines() if p.name == "scheduled-shell")
    assert calls == [p.id]


def test_new_pipeline_graph_deletes_shell_when_editor_cancelled(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("jamais-enregistre", True)))
    _FakeGraphDialog.accept = False
    monkeypatch.setattr("ui.graph_editor.PipelineGraphEditorDialog", _FakeGraphDialog)

    view = PipelinesView()
    view._on_new_pipeline_graph()

    assert db.get_pipelines() == []   # le pipeline coquille n'est pas resté orphelin
