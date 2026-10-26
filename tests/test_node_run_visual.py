"""
DataScheduler — tests/test_node_run_visual.py
C9 (Atelier-echec) : StepNodeItem.set_run_status()/EdgeItem.set_run_state() — les deux nouveaux
états peints qui ne sont ni une sélection ni set_failed() (déjà couvert ailleurs, inchangé).
Vérifie l'état interne (même patron que les tests existants pour set_failed/_is_failed) et qu'un
vrai paint() ne plante pour aucune combinaison, pas le rendu pixel par pixel.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtWidgets import QApplication

from ui.graph_editor.node_item import StepNodeItem
from ui.graph_editor.edge_item import EdgeItem


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _real_paint(item):
    """Un vrai paint() sur un vrai QPixmap — même garde-fou que
    test_selecting_a_node_dims_its_sibling_in_a_real_scene (plante si paint() lève)."""
    rect = item.boundingRect()
    pixmap = QPixmap(max(1, int(rect.width()) + 20), max(1, int(rect.height()) + 20))
    painter = QPainter(pixmap)
    try:
        painter.translate(-rect.left(), -rect.top())
        item.paint(painter, None, None)
    finally:
        painter.end()


# ── StepNodeItem.set_run_status ──────────────────────────

def test_set_run_status_updates_internal_state(qapp):
    node = StepNodeItem({"step_type": "LOCAL_COPY", "config": {"_step_key": "a"}})
    node.set_run_status("✓ 41 s", "success", None)
    assert node._run_status_text == "✓ 41 s"
    assert node._run_status_color_key == "success"
    assert node._run_card_state is None


def test_set_run_status_none_clears_it(qapp):
    node = StepNodeItem({"step_type": "LOCAL_COPY", "config": {"_step_key": "a"}})
    node.set_run_status("non exécutée", "text_dim", "not_executed")
    node.set_run_status(None, None, None)
    assert node._run_status_text is None
    assert node._run_card_state is None


@pytest.mark.parametrize("card_state", [None, "not_executed", "error_triggered"])
@pytest.mark.parametrize("step_type", ["LOCAL_COPY", "CONDITION", "GATEWAY_JOIN"])
def test_paint_does_not_crash_with_any_run_card_state(qapp, card_state, step_type):
    node = StepNodeItem({"step_type": step_type, "config": {"_step_key": "a", "join_mode": "AND"}})
    node.set_run_status("✓ 41 s", "success", card_state)
    _real_paint(node)   # ne doit jamais lever


def test_set_failed_still_wins_over_a_run_card_state(qapp):
    """set_failed() reste la seule source pour l'état FAILED, jamais dupliqué dans
    _run_card_state (voir note d'impact) — les deux peuvent coexister sans incohérence
    puisque node_status_text()/node_card_state() ne renvoient jamais "error_triggered"/
    "not_executed" pour une ligne FAILED."""
    node = StepNodeItem({"step_type": "LOCAL_COPY", "config": {"_step_key": "a"}})
    node.set_run_status("✗ échouée", "danger", None)
    node.set_failed(True)
    _real_paint(node)   # ne doit jamais lever, même combinaison


# ── EdgeItem.set_run_state ───────────────────────────────

def _edge(from_port="output_file"):
    a = StepNodeItem({"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}})
    b = StepNodeItem({"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}})
    b.setPos(300, 0)
    return EdgeItem(a, from_port, b)


def test_set_run_state_updates_internal_state(qapp):
    edge = _edge()
    edge.set_run_state("taken")
    assert edge._run_state == "taken"


@pytest.mark.parametrize("run_state", [None, "taken", "not_taken", "error_waiting", "error_triggered"])
@pytest.mark.parametrize("from_port", ["output_file", "error", "true", "false"])
def test_edge_paint_does_not_crash_with_any_run_state(qapp, run_state, from_port):
    edge = _edge(from_port)
    edge.set_run_state(run_state)
    rect = edge.boundingRect()
    pixmap = QPixmap(max(1, int(rect.width()) + 20), max(1, int(rect.height()) + 20))
    painter = QPainter(pixmap)
    try:
        painter.translate(-rect.left(), -rect.top())
        edge.paint(painter, None, None)
    finally:
        painter.end()
