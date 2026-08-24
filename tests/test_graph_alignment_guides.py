"""
DataScheduler — tests/test_graph_alignment_guides.py
Guides d'alignement pendant le glissé d'un nœud (chantier UX éditeur, Lot 3, A5).

Le glissé interactif d'un QGraphicsItem "ItemIsMovable" repose sur l'accumulation d'un état
interne Qt (dernière position de la souris capturée au press) qui n'est fiable que via un vrai
cycle scène→grabMouse()→évènements — reconstruire cet état à la main avec des
QGraphicsSceneMouseEvent injectés directement sur l'item donne des deltas de position
imprévisibles (confirmé en pratique). Les tests ci-dessous appellent donc directement les
méthodes de production concernées (StepNodeItem.itemChange, PipelineGraphScene.
snap_node_position) plutôt que de simuler la mécanique de glissé de Qt de bout en bout — même
niveau de couverture réelle sur la logique (accrochage, guides, gating sur `_dragging`), sans la
fragilité d'une reconstruction d'état interne Qt non documentée. Seul le déclenchement du flag
`_dragging` lui-même (press/release, qui NE dépend PAS de ce mécanisme de delta) est vérifié via
de vrais évènements construits.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsSceneMouseEvent
import pytest

from ui.graph_editor.graph_scene import PipelineGraphScene, _find_snap
from ui.graph_editor.node_item import StepNodeItem


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ──────────────────────────────────────────────
#  _find_snap() — fonction pure
# ──────────────────────────────────────────────

def test_find_snap_aligns_centers_on_x_axis():
    # Nœud glissé : left=100, width=200 -> centre x=200. Autre nœud : left=194, width=200 ->
    # centre x=294. Écart de centre = 94, hors de portée — on choisit plutôt un cas à portée :
    other = [(100, 300, 200, 64)]   # centre x = 200, identique au nœud glissé
    snap_left, snap_top, guide_x, guide_y = _find_snap(103, 0, 200, 64, other)
    assert snap_left == 100   # recalé pour que son centre (200) coïncide avec l'autre
    assert guide_x == 200
    assert snap_top is None
    assert guide_y is None


def test_find_snap_aligns_edges_on_y_axis():
    # Tous les nœuds de cette app partagent EXACTEMENT la même hauteur (StepNodeItem.HEIGHT) —
    # un écart de "top" est donc toujours numériquement identique à l'écart de "centre"/"bottom"
    # correspondant, les 3 candidats sont à égalité de distance ; peu importe lequel des 3
    # gagne le départage (implémentation), la position résultante est la même dans tous les cas.
    other = [(500, 50, 200, 64)]   # top=50
    snap_left, snap_top, guide_x, guide_y = _find_snap(0, 53, 200, 64, other)
    assert snap_top == 50
    assert guide_y is not None


def test_find_snap_returns_none_when_nothing_within_threshold():
    other = [(1000, 1000, 200, 64)]
    snap_left, snap_top, guide_x, guide_y = _find_snap(0, 0, 200, 64, other)
    assert (snap_left, snap_top, guide_x, guide_y) == (None, None, None, None)


def test_find_snap_prefers_closest_candidate_within_threshold():
    # Deux nœuds à portée sur l'axe Y : top=2 (distance 2) et top=5 (distance 5) depuis top=0 —
    # le plus proche doit l'emporter.
    other = [(500, 5, 200, 64), (900, 2, 200, 64)]
    _, snap_top, _, guide_y = _find_snap(0, 0, 200, 64, other)
    assert snap_top == 2
    assert guide_y is not None


# ──────────────────────────────────────────────
#  PipelineGraphScene.snap_node_position() / guides
# ──────────────────────────────────────────────

def _two_node_scene():
    scene = PipelineGraphScene()
    n1 = StepNodeItem({"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}})
    n1.setPos(0, 0)
    scene.addItem(n1)
    scene.nodes["a"] = n1
    n2 = StepNodeItem({"step_type": "DB_EXTRACT", "config": {"_step_key": "b"}})
    n2.setPos(400, 20)
    scene.addItem(n2)
    scene.nodes["b"] = n2
    return scene, n1, n2


def test_snap_node_position_snaps_and_shows_a_guide(qapp):
    scene, n1, n2 = _two_node_scene()

    result = scene.snap_node_position(n2, QPointF(400, 4))   # top=4, proche du top=0 de n1

    assert result == QPointF(400, 0)
    assert len(scene._alignment_guides) == 2
    v_line, h_line = scene._alignment_guides
    assert not v_line.isVisible()
    assert h_line.isVisible()


def test_snap_node_position_leaves_candidate_unchanged_when_nothing_nearby(qapp):
    scene, n1, n2 = _two_node_scene()

    result = scene.snap_node_position(n2, QPointF(2000, 2000))

    assert result == QPointF(2000, 2000)


def test_clear_alignment_guides_removes_and_empties(qapp):
    scene, n1, n2 = _two_node_scene()
    scene.snap_node_position(n2, QPointF(400, 4))
    assert scene._alignment_guides

    scene.clear_alignment_guides()

    assert scene._alignment_guides == []


def test_scene_mouse_release_clears_any_pending_guides(qapp):
    scene, n1, n2 = _two_node_scene()
    scene.snap_node_position(n2, QPointF(400, 4))
    assert scene._alignment_guides

    ev = QGraphicsSceneMouseEvent(QEvent.GraphicsSceneMouseRelease)
    ev.setButton(Qt.LeftButton)
    ev.setScenePos(QPointF(-9999, -9999))   # loin de tout port, ne doit matcher aucune connexion
    scene.mouseReleaseEvent(ev)

    assert scene._alignment_guides == []


# ──────────────────────────────────────────────
#  StepNodeItem.itemChange() — gating sur _dragging
# ──────────────────────────────────────────────

def test_item_change_snaps_position_while_dragging(qapp):
    scene, n1, n2 = _two_node_scene()
    n2._dragging = True

    result = n2.itemChange(QGraphicsItem.ItemPositionChange, QPointF(400, 4))

    assert result == QPointF(400, 0)


def test_item_change_does_not_snap_when_not_dragging(qapp):
    """setPos() programmatique (rangement automatique, undo, placement initial) ne doit jamais
    déclencher l'accrochage — seul un glissé interactif réel (_dragging=True) le doit."""
    scene, n1, n2 = _two_node_scene()
    assert n2._dragging is False

    result = n2.itemChange(QGraphicsItem.ItemPositionChange, QPointF(400, 4))

    assert result == QPointF(400, 4)
    assert scene._alignment_guides == []


def test_programmatic_set_pos_never_triggers_snap(qapp):
    scene, n1, n2 = _two_node_scene()

    n2.setPos(QPointF(400, 4))   # setPos() direct, comme _on_auto_layout/_on_undo_layout

    assert n2.pos() == QPointF(400, 4)   # jamais réajusté à 0
    assert scene._alignment_guides == []


# ──────────────────────────────────────────────
#  StepNodeItem.mousePressEvent/mouseReleaseEvent — bascule de _dragging
# ──────────────────────────────────────────────

def _mouse_event(event_type, scene_pos, button=Qt.LeftButton):
    ev = QGraphicsSceneMouseEvent(event_type)
    ev.setButton(button)
    ev.setButtons(button)
    ev.setScenePos(scene_pos)
    ev.setPos(scene_pos)
    ev.setLastScenePos(scene_pos)
    ev.setLastPos(scene_pos)
    return ev


def test_mouse_press_sets_dragging_true(qapp):
    scene, n1, n2 = _two_node_scene()
    assert n2._dragging is False

    n2.mousePressEvent(_mouse_event(QEvent.GraphicsSceneMousePress, QPointF(450, 40)))

    assert n2._dragging is True


def test_mouse_release_sets_dragging_false_and_clears_guides(qapp):
    scene, n1, n2 = _two_node_scene()
    n2.mousePressEvent(_mouse_event(QEvent.GraphicsSceneMousePress, QPointF(450, 40)))
    scene.snap_node_position(n2, QPointF(400, 4))
    assert scene._alignment_guides

    n2.mouseReleaseEvent(_mouse_event(QEvent.GraphicsSceneMouseRelease, QPointF(450, 40)))

    assert n2._dragging is False
    assert scene._alignment_guides == []
