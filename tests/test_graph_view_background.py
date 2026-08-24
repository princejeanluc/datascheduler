"""
DataScheduler — tests/test_graph_view_background.py
Fond quadrillé du canevas (chantier identité visuelle) : grille de points en coordonnées de
scène, pour suivre naturellement le panoramique/zoom — même réflexe offscreen Qt que
tests/test_graph_minimap.py pour exercer un vrai repaint sans afficher de fenêtre.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QApplication
import pytest

from ui.graph_editor.graph_scene import PipelineGraphScene
from ui.graph_editor.graph_view import PipelineGraphView


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_draw_background_does_not_crash_on_empty_scene(qapp):
    scene = PipelineGraphScene()
    view = PipelineGraphView(scene)
    pixmap = QPixmap(400, 300)
    painter = QPainter(pixmap)
    try:
        view.drawBackground(painter, QRectF(0, 0, 400, 300))
    finally:
        painter.end()


def test_draw_background_handles_a_rect_not_aligned_to_the_grid(qapp):
    """Le rect visible ne tombe presque jamais exactement sur un multiple de l'espacement —
    l'alignement (left/top arrondis vers le bas) ne doit pas planter ni boucler indéfiniment
    pour un rect décalé ou aux coordonnées négatives (panoramique vers le haut-gauche)."""
    scene = PipelineGraphScene()
    view = PipelineGraphView(scene)
    pixmap = QPixmap(400, 300)
    painter = QPainter(pixmap)
    try:
        view.drawBackground(painter, QRectF(-137.5, -52.3, 401.2, 298.9))
    finally:
        painter.end()
