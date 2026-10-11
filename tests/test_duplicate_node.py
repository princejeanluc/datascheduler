"""
DataScheduler — tests/test_duplicate_node.py
Duplication d'un nœud dans l'éditeur graphique : PipelineGraphScene.duplicate_node() (clé
fraîche, zéro arête, output_name/output_names vidés, position décalée) — les trois déclencheurs
(bouton, raccourci clavier, menu contextuel) sont testés séparément dans
tests/test_graph_tool_rail.py et tests/test_node_context_menu.py.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication
import pytest

from database import db_manager as db
from ui.graph_editor import PipelineGraphEditorDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_duplicate_node_gets_a_fresh_step_key(qapp, test_db):
    pipeline = db.create_pipeline(name="dup-fresh-key-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    node = dlg._scene.add_node({"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
                                QPointF(0, 0))

    copy_node = dlg._scene.duplicate_node(node)

    assert copy_node is not None
    assert copy_node.step_key != "a"
    assert set(dlg._scene.nodes.keys()) == {"a", copy_node.step_key}


def test_duplicate_node_has_no_edges_even_if_original_had_some(qapp, test_db):
    pipeline = db.create_pipeline(name="dup-no-edges-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    edges_before = len(dlg._scene.edges)

    dlg._scene.duplicate_node(dlg._scene.nodes["a"])

    assert len(dlg._scene.edges) == edges_before   # aucune arête ajoutée pour le doublon


def test_duplicate_node_clears_output_name_and_output_names(qapp, test_db):
    pipeline = db.create_pipeline(name="dup-clears-output-name-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    node = dlg._scene.add_node({
        "step_type": "DB_EXTRACT",
        "config": {"_step_key": "a", "output_name": "ventes_csv"},
    }, QPointF(0, 0))

    copy_node = dlg._scene.duplicate_node(node)

    assert copy_node.step["config"]["output_name"] == ""
    assert copy_node.step["config"]["output_names"] == []
    assert node.step["config"]["output_name"] == "ventes_csv"   # l'original reste intact


def test_duplicate_node_lands_offset_not_on_top_of_original(qapp, test_db):
    pipeline = db.create_pipeline(name="dup-offset-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    node = dlg._scene.add_node({"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
                                QPointF(100, 100))

    copy_node = dlg._scene.duplicate_node(node)

    assert copy_node.pos() != node.pos()


def test_duplicate_node_does_not_mutate_original_nested_config():
    """copy.deepcopy(), pas un dict(step) superficiel — une mutation de la copie (après
    duplication) ne doit jamais atteindre l'original via une liste/dict imbriqué partagé."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from ui.graph_editor.graph_scene import PipelineGraphScene

    scene = PipelineGraphScene()
    node = scene.add_node({
        "step_type": "SET_VARIABLE",
        "config": {"_step_key": "a", "assignments": [{"target": "x", "expression": "1"}]},
    }, QPointF(0, 0))

    copy_node = scene.duplicate_node(node)
    copy_node.step["config"]["assignments"].append({"target": "y", "expression": "2"})

    assert len(node.step["config"]["assignments"]) == 1


def test_duplicate_node_with_no_output_name_configured_stays_empty():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from ui.graph_editor.graph_scene import PipelineGraphScene

    scene = PipelineGraphScene()
    node = scene.add_node({"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}}, QPointF(0, 0))

    copy_node = scene.duplicate_node(node)

    assert copy_node.step["config"]["output_name"] == ""


def test_duplicate_selected_duplicates_each_selected_node_independently(qapp, test_db):
    pipeline = db.create_pipeline(name="dup-multi-select-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
    ], edges=[])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    dlg._scene.nodes["a"].setSelected(True)
    dlg._scene.nodes["b"].setSelected(True)
    pos_a_before = dlg._scene.nodes["a"].pos()
    pos_b_before = dlg._scene.nodes["b"].pos()

    dlg._on_duplicate_selected()

    assert len(dlg._scene.nodes) == 4
    new_keys = set(dlg._scene.nodes.keys()) - {"a", "b"}
    assert len(new_keys) == 2
    assert dlg._scene.nodes["a"].pos() == pos_a_before   # les originaux ne bougent pas
    assert dlg._scene.nodes["b"].pos() == pos_b_before
    assert len(dlg._scene.edges) == 0   # aucune arête entre les copies ni avec les originaux


def test_duplicate_selected_with_nothing_selected_is_a_no_op(qapp, test_db):
    pipeline = db.create_pipeline(name="dup-nothing-selected-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
    ], edges=[])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    dlg._on_duplicate_selected()

    assert set(dlg._scene.nodes.keys()) == {"a"}


def test_duplicate_selected_selects_only_the_copies_afterward(qapp, test_db):
    pipeline = db.create_pipeline(name="dup-selects-copies-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
    ], edges=[])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    dlg._scene.nodes["a"].setSelected(True)

    dlg._on_duplicate_selected()

    selected_keys = {n.step_key for n in dlg._scene.selectedItems()}
    assert selected_keys == set(dlg._scene.nodes.keys()) - {"a"}
