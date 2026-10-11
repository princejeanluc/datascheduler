"""
DataScheduler — tests/test_node_item_expand.py
État déplié/replié de StepNodeItem (chantier relooking des nœuds) — bascule, hit-test du
chevron, prepareGeometryChange(). Le contenu peint et la croissance réelle de boundingRect()
sont couverts une fois node_item.py::paint()/boundingRect() reliés à node_facts.py (voir la
suite de ce fichier dans un commit ultérieur du même chantier) ; ici : la mécanique d'état seule.
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
