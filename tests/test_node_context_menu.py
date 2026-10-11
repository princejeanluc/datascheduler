"""
DataScheduler — tests/test_node_context_menu.py
Premier menu contextuel de l'éditeur graphique (chantier duplication de nœud) :
build_node_context_menu() (construction pure, isolée) et le câblage clic-droit →
PipelineGraphEditorDialog._on_node_context_menu() (sélection + ouverture).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QPoint
from PySide6.QtWidgets import QApplication
import pytest

from database import db_manager as db
from ui.graph_editor import PipelineGraphEditorDialog
from ui.graph_editor.node_context_menu import build_node_context_menu


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_menu_has_duplicate_and_delete_actions_wired(qapp, test_db):
    pipeline = db.create_pipeline(name="ctxmenu-actions-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    node = dlg._scene.add_node({"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
                                QPointF(0, 0))
    node.setSelected(True)

    menu = build_node_context_menu(node, dlg)
    labels = [a.text() for a in menu.actions() if a.text()]

    assert "Dupliquer" in labels
    assert "Supprimer" in labels


def test_menu_future_placeholder_is_disabled(qapp, test_db):
    pipeline = db.create_pipeline(name="ctxmenu-future-disabled-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    node = dlg._scene.add_node({"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
                                QPointF(0, 0))

    menu = build_node_context_menu(node, dlg)
    future_action = next(a for a in menu.actions() if a.text() == "(futures actions ici)")

    assert not future_action.isEnabled()


def test_menu_duplicate_action_triggers_duplication(qapp, test_db):
    pipeline = db.create_pipeline(name="ctxmenu-duplicate-trigger-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    node = dlg._scene.add_node({"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
                                QPointF(0, 0))
    node.setSelected(True)

    menu = build_node_context_menu(node, dlg)
    dup_action = next(a for a in menu.actions() if a.text() == "Dupliquer")
    dup_action.trigger()

    assert len(dlg._scene.nodes) == 2


def test_menu_delete_action_triggers_deletion(qapp, test_db):
    pipeline = db.create_pipeline(name="ctxmenu-delete-trigger-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    node = dlg._scene.add_node({"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
                                QPointF(0, 0))
    node.setSelected(True)

    menu = build_node_context_menu(node, dlg)
    del_action = next(a for a in menu.actions() if a.text() == "Supprimer")
    del_action.trigger()

    assert dlg._scene.nodes == {}


def test_right_click_on_unselected_node_selects_it_before_opening_menu(qapp, test_db, monkeypatch):
    pipeline = db.create_pipeline(name="ctxmenu-rightclick-selects-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    node = dlg._scene.add_node({"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
                                QPointF(0, 0))

    opened = []
    # Chantier Atelier Pipelines : _on_node_context_menu() a déménagé vers
    # graph_editor_widget.py — c'est son build_node_context_menu qu'il faut patcher.
    monkeypatch.setattr("ui.graph_editor.graph_editor_widget.build_node_context_menu",
                         lambda n, d: opened.append(n) or type("M", (), {"exec": lambda self, p: None})())

    assert not node.isSelected()
    dlg._on_node_context_menu(node, QPoint(10, 10))

    assert node.isSelected()
    assert opened == [node]


def test_right_click_on_already_selected_node_in_multi_selection_keeps_selection(qapp, test_db, monkeypatch):
    """Un clic-droit sur un nœud qui fait déjà partie d'une sélection multiple volontaire ne
    doit pas la casser — contrairement au cas d'un nœud non sélectionné, qui remplace la
    sélection par lui seul."""
    pipeline = db.create_pipeline(name="ctxmenu-rightclick-keeps-multiselect-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
    ], edges=[])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    dlg._scene.nodes["a"].setSelected(True)
    dlg._scene.nodes["b"].setSelected(True)

    monkeypatch.setattr("ui.graph_editor.graph_editor_widget.build_node_context_menu",
                         lambda n, d: type("M", (), {"exec": lambda self, p: None})())

    dlg._on_node_context_menu(dlg._scene.nodes["a"], QPoint(10, 10))

    assert dlg._scene.nodes["a"].isSelected()
    assert dlg._scene.nodes["b"].isSelected()   # la sélection multiple n'est pas cassée
