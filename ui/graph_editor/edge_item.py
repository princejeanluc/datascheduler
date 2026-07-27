"""
DataScheduler — ui/graph_editor/edge_item.py
Arête entre le port de sortie d'un nœud et le port d'entrée d'un autre — dessinée en courbe de
Bézier, suit les nœuds quand ils sont déplacés (voir PipelineGraphScene.notify_node_moved).
"""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem

from ui.styles import COLORS


class EdgeItem(QGraphicsPathItem):
    """Arête persistée (correspond à une ligne PipelineEdge). `to_port` reste toujours
    "input" côté UI — un seul port d'entrée par nœud dans ce premier jet."""

    def __init__(self, from_node, from_port: str, to_node):
        super().__init__()
        self.from_node = from_node
        self.from_port = from_port
        self.to_node   = to_node
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setZValue(0)
        self.update_path()

    def update_path(self):
        p1 = self.from_node.output_port_pos(self.from_port)
        p2 = self.to_node.input_port_pos()
        path = QPainterPath(p1)
        dx = max(60.0, abs(p2.x() - p1.x()) / 2)
        path.cubicTo(p1.x() + dx, p1.y(), p2.x() - dx, p2.y(), p2.x(), p2.y())
        self.setPath(path)

    def paint(self, painter, option, widget=None):
        color = QColor(COLORS["accent"] if self.isSelected() else COLORS["text_dim"])
        painter.setPen(QPen(color, 2.5 if self.isSelected() else 1.8))
        painter.drawPath(self.path())


class TempEdgeItem(QGraphicsPathItem):
    """Ligne provisoire pendant un drag-to-connect — jamais persistée."""

    def __init__(self, start: QPointF):
        super().__init__()
        self._start = start
        self.setZValue(2)
        self.update_end(start)

    def update_end(self, end: QPointF):
        path = QPainterPath(self._start)
        dx = max(60.0, abs(end.x() - self._start.x()) / 2)
        path.cubicTo(self._start.x() + dx, self._start.y(), end.x() - dx, end.y(),
                     end.x(), end.y())
        self.setPath(path)

    def paint(self, painter, option, widget=None):
        painter.setPen(QPen(QColor(COLORS["accent"]), 2, Qt.DashLine))
        painter.drawPath(self.path())
