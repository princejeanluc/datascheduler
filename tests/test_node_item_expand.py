"""
DataScheduler — tests/test_node_item_expand.py
État déplié/replié de StepNodeItem (chantier relooking des nœuds) — bascule, hit-test du
chevron, prepareGeometryChange(), croissance de boundingRect() et contenu peint une fois relié à
node_facts.py.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtWidgets import QApplication, QGraphicsSceneMouseEvent
import pytest

from ui.graph_editor.node_item import StepNodeItem, _chevron_rect


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _mouse_event(event_type, local_pos, button=Qt.LeftButton):
    # Même patron que tests/test_graph_alignment_guides.py::_mouse_event — construit un
    # évènement appelé directement (hors cycle scène réel), ev.pos() traité comme la position
    # LOCALE à l'item par le code de production (jamais de scène/mapToScene impliqué ici).
    ev = QGraphicsSceneMouseEvent(event_type)
    ev.setButton(button)
    ev.setButtons(button)
    ev.setPos(local_pos)
    ev.setLastPos(local_pos)
    return ev


def _node(step_type="DB_EXTRACT", key="a", label=""):
    return StepNodeItem({"step_type": step_type, "label": label, "config": {"_step_key": key}})


def _chevron_center(node) -> QPointF:
    cx, cy, cw, ch = _chevron_rect(node.WIDTH, node.HEIGHT, node.is_routing_node)
    return QPointF(cx + cw / 2, cy + ch / 2)


# ──────────────────────────────────────────────
#  État de base
# ──────────────────────────────────────────────

def test_node_is_collapsed_by_default(qapp):
    node = _node()
    assert node.is_expanded is False


def test_toggle_expanded_flips_state(qapp):
    node = _node()
    node.toggle_expanded()
    assert node.is_expanded is True
    node.toggle_expanded()
    assert node.is_expanded is False


def test_set_expanded_is_idempotent(qapp):
    node = _node()
    node.set_expanded(True)
    node.set_expanded(True)
    assert node.is_expanded is True


# ──────────────────────────────────────────────
#  prepareGeometryChange() — seul mutateur d'état qui touche la géométrie
# ──────────────────────────────────────────────

def test_set_expanded_calls_prepare_geometry_change(qapp):
    node = _node()
    calls = []
    original = node.prepareGeometryChange
    node.prepareGeometryChange = lambda: (calls.append(True), original())[0]

    node.set_expanded(True)

    assert calls == [True]


def test_set_expanded_to_same_value_does_not_call_prepare_geometry_change(qapp):
    node = _node()   # déjà replié par défaut
    calls = []
    original = node.prepareGeometryChange
    node.prepareGeometryChange = lambda: (calls.append(True), original())[0]

    node.set_expanded(False)   # déjà cet état — aucune mutation

    assert calls == []


def test_set_profile_names_never_calls_prepare_geometry_change(qapp):
    """set_profile_names() ne change jamais le NOMBRE de faits (un ID est juste remplacé par un
    nom dans le texte) — update() suffit, jamais prepareGeometryChange()."""
    node = _node()
    calls = []
    original = node.prepareGeometryChange
    node.prepareGeometryChange = lambda: (calls.append(True), original())[0]

    node.set_profile_names({"ftp": {1: "SFTP_X"}})

    assert calls == []


# ──────────────────────────────────────────────
#  Hit-test du chevron — mousePressEvent
# ──────────────────────────────────────────────

def test_clicking_the_chevron_toggles_expanded_and_does_not_start_a_drag(qapp):
    node = _node()
    assert node._dragging is False

    node.mousePressEvent(_mouse_event(QEvent.GraphicsSceneMousePress, _chevron_center(node)))

    assert node.is_expanded is True
    assert node._dragging is False


def test_clicking_the_chevron_again_collapses(qapp):
    node = _node()
    node.mousePressEvent(_mouse_event(QEvent.GraphicsSceneMousePress, _chevron_center(node)))
    node.mousePressEvent(_mouse_event(QEvent.GraphicsSceneMousePress, _chevron_center(node)))

    assert node.is_expanded is False


def test_clicking_elsewhere_on_the_node_starts_a_drag_and_leaves_expanded_state_unchanged(qapp):
    node = _node()

    node.mousePressEvent(_mouse_event(QEvent.GraphicsSceneMousePress, QPointF(100, 32)))

    assert node._dragging is True
    assert node.is_expanded is False


def test_chevron_hit_test_works_on_a_routing_node_too(qapp):
    node = _node(step_type="CONDITION")
    assert node.is_routing_node is True

    node.mousePressEvent(_mouse_event(QEvent.GraphicsSceneMousePress, _chevron_center(node)))

    assert node.is_expanded is True
    assert node._dragging is False


# ──────────────────────────────────────────────
#  Non-régression
# ──────────────────────────────────────────────

def test_search_text_unaffected_by_expanded_state(qapp):
    node = _node(label="prod_ventes")
    before = node.search_text()
    node.toggle_expanded()
    assert node.search_text() == before


def test_fresh_node_bounding_rect_height_unchanged_by_this_chantier(qapp):
    """Verrou de non-régression : un nœud frais (jamais déplié) garde exactement la même
    hauteur qu'avant ce chantier — HEIGHT + PORT_RADIUS + marge basse, sans le terme
    `extra` additionnel (nul tant que _expanded est False)."""
    from ui.graph_editor.node_item import PORT_RADIUS, _ERROR_LABEL_MARGIN, StepNodeItem as N
    node = _node()
    assert node.boundingRect().height() == pytest.approx(N.HEIGHT + PORT_RADIUS + _ERROR_LABEL_MARGIN)


# ──────────────────────────────────────────────
#  Croissance de boundingRect() une fois déplié (relié à node_facts.py)
# ──────────────────────────────────────────────

def test_bounding_rect_grows_when_expanded(qapp):
    node = _node(step_type="DB_EXTRACT")   # 2 faits (Profil, Requête) via node_facts.py
    collapsed_height = node.boundingRect().height()

    node.set_expanded(True)

    assert node.boundingRect().height() > collapsed_height


def test_bounding_rect_expanded_height_matches_expanded_content_height_exactly(qapp):
    from ui.graph_editor.node_item import PORT_RADIUS, _ERROR_LABEL_MARGIN, _expanded_content_height

    node = _node(step_type="DB_EXTRACT")
    node.set_expanded(True)
    facts, read_vars, written_vars = node._facts_and_vars()
    expected_extra = _expanded_content_height(len(facts), len(read_vars), len(written_vars))

    expected = node.HEIGHT + PORT_RADIUS + _ERROR_LABEL_MARGIN + expected_extra
    assert node.boundingRect().height() == pytest.approx(expected)


def test_bounding_rect_grows_for_routing_node_too(qapp):
    node = _node(step_type="CONDITION")   # 1 fait (Expression)
    collapsed_height = node.boundingRect().height()

    node.set_expanded(True)

    assert node.boundingRect().height() > collapsed_height


def test_gateway_parallel_expanded_still_grows_via_placeholder(qapp):
    """GATEWAY_PARALLEL n'a aucun fait ni variable (config toujours {}) — le contenu déplié
    retombe sur le placeholder générique, boundingRect() grandit quand même (ne lève pas)."""
    node = _node(step_type="GATEWAY_PARALLEL")
    collapsed_height = node.boundingRect().height()

    node.set_expanded(True)

    assert node.boundingRect().height() > collapsed_height


# ──────────────────────────────────────────────
#  Fumée paint() déplié — même patron que test_routing_node_paint_does_not_crash
#  (tests/test_graph_editor_dialog.py)
# ──────────────────────────────────────────────

def _paint_smoke(node):
    from PySide6.QtGui import QPixmap, QPainter as RealQPainter
    rect = node.boundingRect()
    pixmap = QPixmap(int(rect.width()) + 20, int(rect.height()) + 20)
    painter = RealQPainter(pixmap)
    try:
        painter.translate(-rect.left(), -rect.top())
        node.paint(painter, None, None)
    finally:
        painter.end()


def test_paint_does_not_crash_when_expanded_regular_node(qapp):
    node = _node(step_type="FTP_UPLOAD", label="Dépôt quotidien")
    node.set_expanded(True)
    _paint_smoke(node)


def test_paint_does_not_crash_when_expanded_routing_node(qapp):
    node = _node(step_type="CONDITION", label="Seuil atteint ?")
    node.set_expanded(True)
    _paint_smoke(node)


def test_paint_does_not_crash_when_expanded_with_no_facts_or_vars(qapp):
    node = _node(step_type="GATEWAY_PARALLEL")
    node.set_expanded(True)
    _paint_smoke(node)


def test_paint_does_not_crash_when_expanded_with_variable_chips(qapp):
    node = StepNodeItem({
        "step_type": "SET_VARIABLE", "label": "",
        "config": {"_step_key": "a", "assignments": [
            {"target": "limite", "expression": "date_add(var:base_date, -7)"},
        ]},
    })
    node.set_expanded(True)
    _paint_smoke(node)
