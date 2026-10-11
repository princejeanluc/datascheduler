"""
DataScheduler — tests/test_pipelines_view_new_pipeline.py
Fumée (offscreen Qt) : bouton "Nouveau pipeline" de PipelinesView (chantier gouvernance/UX G.4,
puis généralisé comme unique point d'entrée de création lors de la fusion des éditeurs, puis de
nouveau lors du chantier Atelier Pipelines) — crée un pipeline avec juste un nom, puis émet
open_atelier_requested(pipeline_id, None, is_new_pipeline=True) pour que MainWindow ouvre
l'Atelier, sans jamais imposer une étape ou une planification avant de pouvoir enregistrer.

La planification au premier enregistrement du graphe et la suppression de la coquille vide au
retour sans étape (anciennement testées ici via un PipelineGraphEditorDialog factice) sont
désormais la responsabilité d'AtelierPipelinesView — voir
tests/test_atelier_pipelines_view.py::test_new_pipeline_schedules_once_the_graph_is_first_saved
et ::test_new_pipeline_back_without_any_step_deletes_the_shell.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QInputDialog

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_new_pipeline_creates_shell_and_requests_the_atelier(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("mon-pipeline", True)))

    view = PipelinesView()
    captured = []
    view.open_atelier_requested.connect(lambda *args: captured.append(args))

    view._on_new_pipeline()

    pipelines = db.get_pipelines()
    assert len(pipelines) == 1
    assert pipelines[0].name == "mon-pipeline"
    assert len(db.get_steps(pipelines[0].id)) == 0   # pipeline vide, à remplir dans l'Atelier
    assert captured == [(pipelines[0].id, None, True)]


def test_new_pipeline_cancelled_name_prompt_creates_nothing(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))

    view = PipelinesView()
    captured = []
    view.open_atelier_requested.connect(lambda *args: captured.append(args))

    view._on_new_pipeline()

    assert db.get_pipelines() == []
    assert captured == []


def test_new_pipeline_blank_name_creates_nothing(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("   ", True)))

    view = PipelinesView()
    captured = []
    view.open_atelier_requested.connect(lambda *args: captured.append(args))

    view._on_new_pipeline()

    assert db.get_pipelines() == []
    assert captured == []
