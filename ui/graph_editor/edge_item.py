"""
DataScheduler — ui/graph_editor/edge_item.py
Arête entre le port de sortie d'un nœud et le port d'entrée d'un autre — dessinée en courbe de
Bézier, suit les nœuds quand ils sont déplacés (voir PipelineGraphScene.notify_node_moved).
"""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem

from ui.styles import COLORS
from .node_item import _port_visual

# Mot affiché le long d'une liaison "true"/"false" (refonte, lot A-Atelier-grammaire, A5) —
# distinct de l'étiquette courte "V"/"F" du POINT de port (_port_visual, node_item.py) : la
# fiche demande le mot entier sur la liaison elle-même.
_EDGE_PORT_WORD = {"true": "vrai", "false": "faux"}


def edge_base_visual(from_port: str) -> tuple[str, bool]:
    """Couleur de base (clé COLORS) + pointillé ou non pour une liaison, d'après son port de
    départ (refonte, lot A-Atelier-grammaire, A5) — fonction pure, testable sans Qt (même
    philosophie que node_item.py::_port_visual/_tinted_bg). Ne tient pas compte de l'état
    (sélection/exécution/échec), toujours prioritaire sur cette base dans paint()."""
    color_key, _ = _port_visual(from_port)
    return color_key, from_port == "error"


def edge_selection_color_key(from_port: str) -> str:
    """Couleur (clé COLORS) d'une liaison qui touche le nœud sélectionné (A4) — accent, sauf son
    propre chemin d'erreur qui passe en warning plutôt qu'accent (la fiche distingue les deux
    explicitement). Fonction pure, même philosophie que edge_base_visual."""
    return "warning" if from_port == "error" else "accent"

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
        # Couleur/pointillé de base par port (A5) — l'état (sélection/exécution/échec) reste
        # toujours prioritaire sur cette base.
        base_color_key, base_dashed = edge_base_visual(self.from_port)

        # A4 : une liaison touchant le nœud sélectionné (pas seulement la liaison elle-même
        # sélectionnée) passe en accent — sauf son propre chemin d'erreur, qui passe en warning
        # plutôt qu'accent (la fiche distingue explicitement les deux).
        node_selected = self.from_node.isSelected() or self.to_node.isSelected()
        selected = self.isSelected() or node_selected

        if self._is_failed:
            color = QColor(COLORS["danger"])
        elif self._is_executing:
            color = QColor(COLORS["signal"])
        elif selected:
            color = QColor(COLORS[edge_selection_color_key(self.from_port)])
        else:
            color = QColor(COLORS[base_color_key])
        state_active = selected or self._is_executing or self._is_failed
        pen = QPen(color, 2.5 if state_active else 1.8)
        if base_dashed and not state_active:
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.drawPath(self.path())

        # Mot "vrai"/"faux" le long de la liaison (A5) — à 55% du tracé (jamais près du départ,
        # où un losange concentre souvent 2-3 ports colorés proches de son sommet droit : un mot
        # posé juste à côté se chevauchait avec eux), décalé au-dessus de la courbe.
        word = _EDGE_PORT_WORD.get(self.from_port)
        if word:
            # Distance fixe depuis le départ (25px, ou la moitié du tracé s'il est plus court)
            # plutôt qu'un pourcentage : un pourcentage fixe plaçait le mot dans le sommet du
            # losange de départ sur une liaison courte (chevauchait les autres ports du même
            # sommet) ou carrément sous le nœud d'arrivée suivant (caché derrière sa forme,
            # peinte par-dessus) — constaté en capturant deux nœuds proches l'un de l'autre.
            path = self.path()
            length = min(25.0, path.length() / 2)
            pt = path.pointAtPercent(path.percentAtLength(length))
            font = painter.font(); font.setBold(True); font.setPointSize(7)
            painter.setFont(font)
            painter.setPen(QColor(COLORS[base_color_key]))
            # "vrai" au-dessus de son tracé, "faux" en dessous du sien : les deux ports partent
            # du même sommet de losange, assez proches pour que les deux mots se chevauchent à
            # une distance fixe du départ si les deux sont placés du même côté (constaté en
            # capturant) — les écarter verticalement les sépare sans dépendre de la géométrie
            # exacte de chaque tracé.
            y_offset = -9 if self.from_port == "true" else 14
            painter.drawText(QPointF(pt.x() - 6, pt.y() + y_offset), word)

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
