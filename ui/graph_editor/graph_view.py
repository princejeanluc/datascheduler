"""
DataScheduler — ui/graph_editor/graph_view.py
Vue du canevas : zoom à la molette, sélection par rectangle sur fond vide (glisser un nœud
reste possible car ItemIsMovable prend la main sur le clic quand il tombe sur un item).
"""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QGraphicsView

from ui.styles import COLORS

_GRID_SPACING = 24
_GRID_DOT_WIDTH = 2.0


class PipelineGraphView(QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        # Mini-carte (chantier UX éditeur, Lot 2, A3) et rail d'icônes (chantier chrome de
        # l'éditeur) — enregistrés par le dialogue après construction, jamais créés ici (la vue
        # ne les connaît pas, elle se contente de les notifier des évènements pertinents).
        self._minimap = None
        self._rail = None

    def drawBackground(self, painter, rect):
        # Grille de points en coordonnées de SCÈNE (pas d'écran) — chantier identité visuelle,
        # maquette approuvée : suit naturellement le panoramique et le zoom, comme Figma/Miro,
        # plutôt qu'un motif fixe à l'écran qui glisserait sous le contenu. Un seul drawPoints()
        # (pas un drawEllipse() par point) — la grille peut couvrir plusieurs centaines de points
        # selon la taille de la fenêtre, un appel par point serait inutilement coûteux à chaque
        # repaint (glissé, zoom).
        painter.fillRect(rect, QColor(COLORS["bg_main"]))

        dot_color = QColor(COLORS["border"])
        dot_color.setAlpha(140)
        pen = QPen(dot_color, _GRID_DOT_WIDTH)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)

        left = int(rect.left()) - (int(rect.left()) % _GRID_SPACING)
        top  = int(rect.top())  - (int(rect.top())  % _GRID_SPACING)
        points = []
        x = left
        while x < rect.right():
            y = top
            while y < rect.bottom():
                points.append(QPointF(x, y))
                y += _GRID_SPACING
            x += _GRID_SPACING
        if points:
            painter.drawPoints(points)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)
        if self._minimap is not None:
            self._minimap.request_repaint()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._minimap is not None:
            self._minimap.reposition()
        if self._rail is not None:
            self._rail.reposition()
