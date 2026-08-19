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


def test_edge_item_arrow_points_toward_the_target_node(qapp):
    """Flèche de direction (chantier identité, vague 1, idée 14a) — la pointe recule juste avant
    le port d'entrée sans le chevaucher, et le triangle pointe vers +x (la tangente en fin de
    tracé est toujours horizontale par construction de update_path())."""
    from_node = StepNodeItem({"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}})
    to_node = StepNodeItem({"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}})
    to_node.setPos(400, 0)
    edge = EdgeItem(from_node, "output_file", to_node)

    tip, base1, base2 = edge._arrow_points()
    input_x = to_node.input_port_pos().x()

    assert tip.x() < input_x
    assert base1.x() < tip.x() and base2.x() < tip.x()
    assert base1.y() < tip.y() < base2.y() or base2.y() < tip.y() < base1.y()


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


def test_set_executing_step_key_highlights_node_and_incoming_edges(qapp, test_db):
    """Traçage lumineux (chantier identité, vague 4, idée 14b) : surligne le nœud en cours
    d'exécution + ses arêtes entrantes, retire le surlignage précédent au changement d'étape."""
    pipeline = db.create_pipeline(name="trace-glow-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
        {"step_type": "FTP_UPLOAD", "config": {"_step_key": "c"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
        {"from_step_key": "b", "from_port": "output_file", "to_step_key": "c", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    scene = dlg._scene
    edge_ab = next(e for e in scene.edges if e.from_node is scene.nodes["a"])
    edge_bc = next(e for e in scene.edges if e.from_node is scene.nodes["b"])

    scene.set_executing_step_key("b")
    assert scene.nodes["b"]._is_executing
    assert not scene.nodes["a"]._is_executing
    assert edge_ab._is_executing    # entrante vers b
    assert not edge_bc._is_executing   # sortante de b, pas entrante

    scene.set_executing_step_key("c")
    assert not scene.nodes["b"]._is_executing
    assert not edge_ab._is_executing
    assert scene.nodes["c"]._is_executing
    assert edge_bc._is_executing

    scene.set_executing_step_key(None)   # run terminé — plus rien surligné
    assert not scene.nodes["c"]._is_executing
    assert not edge_bc._is_executing


def test_set_executing_step_key_unknown_key_is_a_no_op(qapp, test_db):
    pipeline = db.create_pipeline(name="trace-glow-unknown-key")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
    ], edges=[])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    dlg._scene.set_executing_step_key("does-not-exist")   # ne doit pas lever d'exception
    assert not dlg._scene.nodes["a"]._is_executing


def test_poll_executing_step_calls_scene_with_running_step_key(qapp, test_db, monkeypatch):
    """Le QTimer de polling interroge get_running_step_keys() et répercute le résultat sur la
    scène — vérifié directement sur la méthode plutôt qu'en attendant un vrai déclenchement du
    QTimer (pas d'exécution réelle de pipeline dans ce test)."""
    pipeline = db.create_pipeline(name="trace-glow-poll")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
    ], edges=[])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    monkeypatch.setattr(db, "get_running_step_keys", lambda: {pipeline.id: "a"})
    dlg._poll_executing_step()
    assert dlg._scene.nodes["a"]._is_executing

    monkeypatch.setattr(db, "get_running_step_keys", lambda: {})
    dlg._poll_executing_step()
    assert not dlg._scene.nodes["a"]._is_executing


def test_incoming_prior_steps_returns_only_connected_upstream_steps(qapp, test_db):
    """Régression : _on_add_step()/_on_node_double_clicked() passaient prior_steps=[] en dur au
    dialogue de config d'étape, donc le sélecteur "Source"/bouton "+ Artefact" (chantier 3)
    n'affichaient jamais les étapes réellement connectées dans l'éditeur graphique (toujours
    "étape précédente (par défaut)", contrairement à l'éditeur linéaire où prior_steps a toujours
    été correctement rempli)."""
    pipeline = db.create_pipeline(name="incoming-prior-steps-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "b"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "c"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "c", "to_port": "input"},
        {"from_step_key": "b", "from_port": "output_file", "to_step_key": "c", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    prior = dlg._incoming_prior_steps(dlg._scene.nodes["c"])
    assert {s["config"]["_step_key"] for s in prior} == {"a", "b"}

    # "a" n'a aucune arête entrante — sa liste doit rester vide, pas celle du nœud "c".
    assert dlg._incoming_prior_steps(dlg._scene.nodes["a"]) == []


def test_on_node_double_clicked_passes_connected_steps_to_config_dialog(qapp, test_db, monkeypatch):
    from PySide6.QtWidgets import QDialog
    import ui.step_editor as step_editor_module

    pipeline = db.create_pipeline(name="double-click-prior-steps-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    captured = {}

    class _FakeConfigDialog:
        def exec(self):
            return QDialog.Rejected

    def _fake_open_config_dialog(*args, **kwargs):
        captured["prior_steps"] = kwargs.get("prior_steps")
        return _FakeConfigDialog()

    monkeypatch.setattr(step_editor_module, "_open_config_dialog", _fake_open_config_dialog)

    dlg._on_node_double_clicked(dlg._scene.nodes["b"])

    assert [s["config"]["_step_key"] for s in captured["prior_steps"]] == ["a"]


def test_on_add_step_passes_all_scene_steps_as_prior_steps(qapp, test_db, monkeypatch):
    """À l'ajout, le nouveau nœud n'a encore aucune arête (il n'existe pas sur le canevas) — même
    souplesse que l'éditeur linéaire à l'ajout (prior_steps=self._steps_data, la liste complète) :
    tous les nœuds déjà présents sont proposés, à connecter ensuite par glisser-déposer."""
    from PySide6.QtWidgets import QDialog
    import ui.step_editor as step_editor_module
    from ui.step_editor.step_type_chooser_dialog import StepTypeChooserDialog

    pipeline = db.create_pipeline(name="add-step-prior-steps-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
    ], edges=[])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    monkeypatch.setattr(StepTypeChooserDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(StepTypeChooserDialog, "chosen_type", "LOCAL_COPY", raising=False)

    captured = {}

    class _FakeConfigDialog:
        def exec(self):
            return QDialog.Rejected

    def _fake_open_config_dialog(*args, **kwargs):
        captured["prior_steps"] = kwargs.get("prior_steps")
        return _FakeConfigDialog()

    monkeypatch.setattr(step_editor_module, "_open_config_dialog", _fake_open_config_dialog)

    dlg._on_add_step()

    assert [s["config"]["_step_key"] for s in captured["prior_steps"]] == ["a"]


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
