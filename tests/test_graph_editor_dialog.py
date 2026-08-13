"""
DataScheduler — tests/test_graph_editor_dialog.py
Fumée : PipelineGraphEditorDialog s'ouvre sans erreur (offscreen Qt, même réflexe que
tests/test_export_dialog.py et tests/test_step_editor_dialogs.py), charge correctement un
graphe déjà enregistré, et le round-trip charger/modifier/enregistrer préserve steps et edges.
Pas de simulation de drag souris réelle (hors de portée raisonnable d'un test automatisé) —
les interactions scene.add_node()/add_edge()/remove_node() sont exercées directement, ce sont
elles que le drag-to-connect appelle en interne (voir ui/graph_editor/graph_scene.py).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
import pytest

from database import db_manager as db
from ui.graph_editor import PipelineGraphEditorDialog
from ui.graph_editor.node_item import StepNodeItem
from ui.graph_editor.edge_item import EdgeItem


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_dialog_opens_on_empty_pipeline(qapp, test_db):
    pipeline = db.create_pipeline(name="empty")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    assert dlg.windowTitle()
    assert dlg._scene.nodes == {}
    assert dlg._scene.edges == []


def test_dialog_loads_existing_graph(qapp, test_db):
    pipeline = db.create_pipeline(name="loaded-graph")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "CONDITION", "config": {"_step_key": "b", "expression": "rows_count > 0"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "c"}},
        {"step_type": "FTP_UPLOAD", "config": {"_step_key": "d"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
        {"from_step_key": "b", "from_port": "true", "to_step_key": "c", "to_port": "input"},
        {"from_step_key": "b", "from_port": "false", "to_step_key": "d", "to_port": "input"},
    ])

    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    assert set(dlg._scene.nodes.keys()) == {"a", "b", "c", "d"}
    assert len(dlg._scene.edges) == 3
    for node in dlg._scene.nodes.values():
        assert isinstance(node, StepNodeItem)
    for edge in dlg._scene.edges:
        assert isinstance(edge, EdgeItem)

    condition_node = dlg._scene.nodes["b"]
    assert condition_node.output_ports == ("true", "false")


def test_add_node_cascades_position_and_saves(qapp, test_db):
    pipeline = db.create_pipeline(name="add-node-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    node1 = dlg._scene.add_node(
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "x"}}, dlg._next_new_node_pos()
    )
    pos2 = dlg._next_new_node_pos()
    node2 = dlg._scene.add_node(
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "y"}}, pos2
    )
    assert pos2.x() > node1.pos().x()

    edge = dlg._scene.add_edge("x", "output_file", "y")
    assert edge is not None

    dlg._on_save()

    saved_steps = db.get_steps(pipeline.id)
    saved_edges = db.get_edges(pipeline.id)
    assert len(saved_steps) == 2
    assert len(saved_edges) == 1
    assert {s.pos_x for s in saved_steps} == {int(node1.pos().x()), int(node2.pos().x())}


def test_editing_node_updates_step_dict(qapp, test_db):
    pipeline = db.create_pipeline(name="edit-node-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
    ], edges=[])

    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    node = dlg._scene.nodes["a"]

    # Simule ce que _on_node_double_clicked ferait après confirmation du dialogue de config
    # (sans passer par le vrai double-clic souris) — même config, mais avec un libellé.
    node.step = {**node.step, "label": "Ma source"}
    node.update()

    dlg._on_save()
    reloaded = db.get_steps(pipeline.id)
    assert reloaded[0].label == "Ma source"


def test_remove_node_removes_connected_edges_before_save(qapp, test_db):
    pipeline = db.create_pipeline(name="remove-node-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
    ])

    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    assert len(dlg._scene.edges) == 1

    dlg._scene.remove_node(dlg._scene.nodes["b"])
    assert len(dlg._scene.edges) == 0
    assert "b" not in dlg._scene.nodes

    dlg._on_save()
    assert len(db.get_steps(pipeline.id)) == 1
    assert len(db.get_edges(pipeline.id)) == 0


def test_schedule_button_opens_linear_editor_and_refreshes_title(qapp, test_db, monkeypatch):
    """Raccourci ajouté après le chantier de déclenchement conditionnel — évite l'aller-retour
    "fermer, retrouver la ligne, cliquer Modifier" juste pour la planification/le déclenchement,
    que ce dialogue ne gère pas lui-même."""
    from PySide6.QtWidgets import QDialog
    import ui.step_editor as step_editor_module

    pipeline = db.create_pipeline(name="schedule-shortcut-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    captured = {}
    class _FakeLinearEditor:
        def __init__(self, parent, pipeline):
            captured["pipeline_id"] = pipeline.id

        def exec(self):
            # Simule un renommage effectué dans l'éditeur classique, comme le ferait un vrai
            # PipelineEditorDialog._on_save().
            db.update_pipeline(pipeline.id, name="renamed-via-linear-editor")
            return QDialog.Accepted

    monkeypatch.setattr(step_editor_module, "PipelineEditorDialog", _FakeLinearEditor)

    dlg._on_open_schedule_dialog()

    assert captured["pipeline_id"] == pipeline.id
    assert dlg._pipeline.name == "renamed-via-linear-editor"
    assert "renamed-via-linear-editor" in dlg.windowTitle()
