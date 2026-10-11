"""
DataScheduler — tests/test_pipeline_step_dag_thumbnail.py
Vignette mini-DAG par rang (chantier Atelier Pipelines, écran 1) — remplace la chaîne plate de
PipelineFlowThumbnail. _layout_step_dag_thumbnail est de la géométrie pure (testable sans Qt) ;
PipelineStepDagThumbnail n'est testé qu'en construction/absence d'exception (même patron que
test_pipeline_flow_thumbnail_handles_zero_one_and_many_colors et
test_layout_topology_nodes_keeps_a_chain_on_one_row dans
test_history_status_filter_and_navigation.py).
"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _edge(frm, to):
    return {"from_step_key": frm, "to_step_key": to}


# ──────────────────────────────────────────────
#  _layout_step_dag_thumbnail — géométrie pure
# ──────────────────────────────────────────────

def test_layout_linear_chain_increases_column_per_step():
    from ui.main_window.widgets import _layout_step_dag_thumbnail

    positions = _layout_step_dag_thumbnail(["a", "b", "c"], [_edge("a", "b"), _edge("b", "c")])

    assert positions == {"a": (0, 0), "b": (1, 0), "c": (2, 0)}


def test_layout_branches_share_the_same_column_on_different_rows():
    from ui.main_window.widgets import _layout_step_dag_thumbnail

    # a -> b, a -> c : b et c sont deux branches parallèles, même rang (1), lignes différentes.
    positions = _layout_step_dag_thumbnail(["a", "b", "c"], [_edge("a", "b"), _edge("a", "c")])

    assert positions["a"] == (0, 0)
    assert {positions["b"], positions["c"]} == {(1, 0), (1, 1)}


def test_layout_disconnected_steps_all_land_on_rank_zero():
    from ui.main_window.widgets import _layout_step_dag_thumbnail

    positions = _layout_step_dag_thumbnail(["a", "b"], [])

    assert positions["a"][0] == 0
    assert positions["b"][0] == 0


def test_layout_returns_none_on_cycle():
    from ui.main_window.widgets import _layout_step_dag_thumbnail

    assert _layout_step_dag_thumbnail(["a", "b"], [_edge("a", "b"), _edge("b", "a")]) is None


# ──────────────────────────────────────────────
#  PipelineStepDagThumbnail — construction/rendu sans exception
# ──────────────────────────────────────────────

def _node(key, color="#FF7900", is_routing=False):
    return {"step_key": key, "color": color, "is_routing": is_routing}


def test_thumbnail_handles_zero_one_and_many_nodes(qapp):
    from ui.main_window.widgets import PipelineStepDagThumbnail

    PipelineStepDagThumbnail([], [])
    PipelineStepDagThumbnail([_node("a")], [])
    w = PipelineStepDagThumbnail(
        [_node("a"), _node("b"), _node("c")],
        [_edge("a", "b"), _edge("b", "c")],
    )
    w.repaint()


def test_thumbnail_renders_routing_nodes_as_diamonds_without_raising(qapp):
    from ui.main_window.widgets import PipelineStepDagThumbnail

    w = PipelineStepDagThumbnail(
        [_node("a"), _node("b", is_routing=True), _node("c")],
        [_edge("a", "b"), _edge("b", "c")],
    )
    w.repaint()


def test_thumbnail_falls_back_to_dot_chain_on_cycle_without_raising(qapp):
    from ui.main_window.widgets import PipelineStepDagThumbnail

    w = PipelineStepDagThumbnail(
        [_node("a"), _node("b")],
        [_edge("a", "b"), _edge("b", "a")],
    )
    w.repaint()


def test_thumbnail_truncates_a_rank_with_more_nodes_than_max_visible_rows(qapp):
    from ui.main_window.widgets import PipelineStepDagThumbnail

    # 5 branches parallèles depuis "a" : au-delà de MAX_VISIBLE_ROWS, un "+N" doit être dessiné
    # plutôt que de faire déborder la vignette hors de la cellule du tableau.
    nodes = [_node("a")] + [_node(f"b{i}") for i in range(5)]
    edges = [_edge("a", f"b{i}") for i in range(5)]
    w = PipelineStepDagThumbnail(nodes, edges)
    w.repaint()


def test_set_data_updates_width(qapp):
    from ui.main_window.widgets import PipelineStepDagThumbnail

    w = PipelineStepDagThumbnail([_node("a")], [])
    width_one = w.width()
    w.set_data([_node("a"), _node("b"), _node("c")], [_edge("a", "b"), _edge("b", "c")])
    assert w.width() > width_one
