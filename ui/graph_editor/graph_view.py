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

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)
