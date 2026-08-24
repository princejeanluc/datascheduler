"""
DataScheduler — ui/graph_editor/edge_item.py
Arête entre le port de sortie d'un nœud et le port d'entrée d'un autre — dessinée en courbe de
Bézier, suit les nœuds quand ils sont déplacés (voir PipelineGraphScene.notify_node_moved).
"""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem

from ui.styles import COLORS

# Géométrie de la pointe de flèche — la tangente en fin de tracé (update_path()) est toujours
# strictement horizontale par construction (le point de contrôle d'arrivée a la même ordonnée
# que le point d'arrivée), donc une flèche droite pointant vers +x reste correcte quels que
# soient les positions réelles des nœuds, sans calcul de dérivée bézier.
_ARROW_LENGTH = 9
_ARROW_HALF_WIDTH = 4.5
_ARROW_OFFSET = 7   # recule la pointe pour ne pas chevaucher le port d'entrée


class EdgeItem(QGraphicsPathItem):
    """Arête persistée (correspond à une ligne PipelineEdge). `to_port` reste toujours
    "input" côté UI — un seul port d'entrée par nœud dans ce premier jet."""

    def __init__(self, from_node, from_port: str, to_node):
        super().__init__()
        self.from_node = from_node
        self.from_port = from_port
        self.to_node   = to_node
        self._is_executing = False
        self._is_failed    = False
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setZValue(0)
        self.update_path()

    def set_executing(self, executing: bool) -> None:
        """Traçage lumineux (chantier identité visuelle) : surligne cette arête comme entrante
        vers l'étape en cours d'une exécution réelle. Voir StepNodeItem.set_executing()."""
        if executing != self._is_executing:
            self._is_executing = executing
            self.update()

    def set_failed(self, failed: bool) -> None:
        """Surlignage "échec" (chantier UX éditeur, Lot 1, B1) — état JUMEAU de set_executing(),
        jamais une réutilisation : celui-ci peint en rouge (COLORS["danger"]), pas en bleu
        "signal" (qui affirmerait à tort qu'une étape terminée est en train de tourner)."""
        if failed != self._is_failed:
            self._is_failed = failed
            self.update()

    def update_path(self):
        p1 = self.from_node.output_port_pos(self.from_port)
        p2 = self.to_node.input_port_pos()
        path = QPainterPath(p1)
        dx = max(60.0, abs(p2.x() - p1.x()) / 2)
        path.cubicTo(p1.x() + dx, p1.y(), p2.x() - dx, p2.y(), p2.x(), p2.y())
        self.setPath(path)

    def _arrow_points(self) -> tuple[QPointF, QPointF, QPointF]:
        """Pointe + 2 points de base du triangle de flèche, juste avant le port d'entrée."""
        p2 = self.to_node.input_port_pos()
        tip = QPointF(p2.x() - _ARROW_OFFSET, p2.y())
        base1 = QPointF(tip.x() - _ARROW_LENGTH, tip.y() - _ARROW_HALF_WIDTH)
        base2 = QPointF(tip.x() - _ARROW_LENGTH, tip.y() + _ARROW_HALF_WIDTH)
        return tip, base1, base2

    def paint(self, painter, option, widget=None):
        if self._is_failed:
            color = QColor(COLORS["danger"])
        elif self._is_executing:
            color = QColor(COLORS["signal"])
        elif self.isSelected():
            color = QColor(COLORS["accent"])
        else:
            color = QColor(COLORS["text_dim"])
        painter.setPen(QPen(
            color, 2.5 if (self.isSelected() or self._is_executing or self._is_failed) else 1.8
        ))
        painter.drawPath(self.path())

        tip, base1, base2 = self._arrow_points()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPolygon(QPolygonF([tip, base1, base2]))


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
