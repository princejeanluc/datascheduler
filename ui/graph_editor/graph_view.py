"""
DataScheduler — ui/graph_editor/graph_view.py
Vue du canevas : zoom à la molette, sélection par rectangle sur fond vide (glisser un nœud
reste possible car ItemIsMovable prend la main sur le clic quand il tombe sur un item).
"""

from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGraphicsView


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
