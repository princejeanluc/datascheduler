"""
DataScheduler — tests/test_pipeline_topology_dialog.py
Fumée (offscreen Qt) : PipelineTopologyDialog s'ouvre sans erreur, affiche un nœud par pipeline
relié par les chaînes de déclenchement, la recherche/le filtre de statut réduisent bien le
nombre de nœuds affichés, et cliquer un nœud déclenche l'ouverture du détail attendu (chantier
"Vue globale des pipelines", suite de la vague 3 identité).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _node_items(dlg):
    from ui.dialogs.pipeline_topology_dialog import PipelineNodeItem
    return [i for i in dlg._scene.items() if isinstance(i, PipelineNodeItem)]


def test_dialog_shows_one_node_per_pipeline(qapp, test_db):
    from ui.dialogs import PipelineTopologyDialog

    db.create_pipeline(name="topo-a")
    db.create_pipeline(name="topo-b")

    dlg = PipelineTopologyDialog(None, db.get_pipelines())
    assert len(_node_items(dlg)) == 2


def test_dialog_draws_an_edge_for_a_trigger_chain(qapp, test_db):
    from ui.dialogs import PipelineTopologyDialog
    from ui.dialogs.pipeline_topology_dialog import PipelineEdgeItem

    p1 = db.create_pipeline(name="topo-parent")
    p2 = db.create_pipeline(name="topo-child")
    db.set_pipeline_trigger(p2.id, p1.id, "SUCCESS")

    dlg = PipelineTopologyDialog(None, db.get_pipelines())
    edges = [i for i in dlg._scene.items() if isinstance(i, PipelineEdgeItem)]
    assert len(edges) == 1


def test_search_filters_nodes_by_name(qapp, test_db):
    from ui.dialogs import PipelineTopologyDialog

    db.create_pipeline(name="alpha-pipeline")
    db.create_pipeline(name="beta-pipeline")

    dlg = PipelineTopologyDialog(None, db.get_pipelines())
    assert len(_node_items(dlg)) == 2

    dlg.inp_search.setText("alpha")
    assert len(_node_items(dlg)) == 1


def test_status_filter_isolates_inactive_pipelines(qapp, test_db):
    from ui.dialogs import PipelineTopologyDialog

    active = db.create_pipeline(name="topo-active")
    inactive = db.create_pipeline(name="topo-inactive")
    db.set_pipeline_active(inactive.id, False)

    dlg = PipelineTopologyDialog(None, db.get_pipelines())
    idx = dlg.cb_status.findData("INACTIVE")
    dlg.cb_status.setCurrentIndex(idx)

    nodes = _node_items(dlg)
    assert len(nodes) == 1
    assert nodes[0].pipeline.id == inactive.id


def test_clicking_a_node_opens_pipeline_detail_dialog(qapp, test_db, monkeypatch):
    import ui.dialogs as dialogs_module
    from ui.dialogs import PipelineTopologyDialog

    p = db.create_pipeline(name="topo-clickable")

    opened = {}
    class _FakeDetailDialog:
        def __init__(self, parent, pipeline):
            opened["pipeline_id"] = pipeline.id
        def exec(self):
            opened["exec_called"] = True

    # _on_node_clicked() fait un import local `from ui.dialogs import PipelineDetailDialog` —
    # même patron que test_graph_editor_dialog.py::test_schedule_button_opens_linear_editor_...,
    # on patch donc l'attribut du PACKAGE ui.dialogs, pas du module pipeline_topology_dialog.
    monkeypatch.setattr(dialogs_module, "PipelineDetailDialog", _FakeDetailDialog)

    dlg = PipelineTopologyDialog(None, db.get_pipelines())
    dlg._on_node_clicked(p.id)

    assert opened.get("pipeline_id") == p.id
    assert opened.get("exec_called") is True
