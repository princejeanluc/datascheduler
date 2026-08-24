"""
DataScheduler — tests/test_graph_view_pan.py
Pan manuel au clic milieu (chantier identité visuelle) : événements construits directement et
livrés aux gestionnaires de PipelineGraphView (pas de vraie boucle d'évènements Qt — même réflexe
que le reste de ce module, aucune simulation de glissé souris via QTest). Le clic gauche
(sélection-rectangle, glisser-déposer, glisser-pour-connecter) est géré par
PipelineGraphScene, jamais touché ici — vérifié en confirmant que le clic milieu n'atteint jamais
la scène.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
import pytest

from ui.graph_editor.graph_scene import PipelineGraphScene
from ui.graph_editor.graph_view import PipelineGraphView
from ui.graph_editor.node_item import StepNodeItem


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _mouse_event(event_type, pos, button):
    local = QPointF(*pos)
    return QMouseEvent(event_type, local, local, button, button, Qt.NoModifier)


def _make_view_with_content(qapp):
    scene = PipelineGraphScene()
    for i in range(6):
        node = StepNodeItem({"step_type": "DB_EXTRACT", "config": {"_step_key": f"n{i}"}})
        node.setPos(i * 400, i * 200)
        scene.addItem(node)
        scene.nodes[f"n{i}"] = node
    # Scène explicitement plus grande que le viewport — sinon la plage des barres de défilement
    # peut rester [0,0] tant que Qt n'a pas fait un premier vrai cycle d'affichage (jamais le cas
    # ici, offscreen, sans show()), rendant tout setValue() un no-op indépendamment du pan.
    scene.setSceneRect(0, 0, 3000, 1500)
    view = PipelineGraphView(scene)
    view.resize(300, 200)
    # Garde une référence Python forte sur `scene` au-delà du retour de cette fonction — PySide6
    # ne garantit pas que QGraphicsView(scene) suffise à empêcher le wrapper Python de `scene`
    # d'être ramassé, ce qui invaliderait le sceneRect fixé ci-dessus dès que cette fonction se
    # termine (piège déjà rencontré ailleurs dans cette base : le parent Qt ne protège pas les
    # attributs/références Python de la collecte).
    view._test_scene_ref = scene
    return view


def test_middle_button_press_starts_panning_and_sets_cursor(qapp):
    view = _make_view_with_content(qapp)
    view.mousePressEvent(_mouse_event(QEvent.MouseButtonPress, (10, 10), Qt.MiddleButton))
    assert view._panning is True
    assert view.cursor().shape() == Qt.ClosedHandCursor


def test_middle_button_drag_moves_scrollbars(qapp):
    view = _make_view_with_content(qapp)
    view.mousePressEvent(_mouse_event(QEvent.MouseButtonPress, (100, 100), Qt.MiddleButton))
    h_before = view.horizontalScrollBar().value()
    v_before = view.verticalScrollBar().value()

    view.mouseMoveEvent(_mouse_event(QEvent.MouseMove, (60, 70), Qt.MiddleButton))

    h_after = view.horizontalScrollBar().value()
    v_after = view.verticalScrollBar().value()
    assert (h_after, v_after) != (h_before, v_before)


def test_middle_button_release_stops_panning(qapp):
    view = _make_view_with_content(qapp)
    view.mousePressEvent(_mouse_event(QEvent.MouseButtonPress, (10, 10), Qt.MiddleButton))
    view.mouseReleaseEvent(_mouse_event(QEvent.MouseButtonRelease, (10, 10), Qt.MiddleButton))
    assert view._panning is False


def test_left_button_press_never_starts_panning(qapp):
    """Le clic gauche reste entièrement géré par PipelineGraphScene (sélection-rectangle,
    glisser-déposer, glisser-pour-connecter) — jamais intercepté par le pan."""
    view = _make_view_with_content(qapp)
    view.mousePressEvent(_mouse_event(QEvent.MouseButtonPress, (10, 10), Qt.LeftButton))
    assert view._panning is False
