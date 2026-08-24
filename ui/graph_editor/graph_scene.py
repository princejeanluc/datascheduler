"""
DataScheduler — ui/graph_editor/graph_scene.py
Scène du canevas : centralise l'état d'interaction (drag-to-connect, suppression). Pas de classe
PortItem séparée — les ports sont de petites zones de tolérance calculées sur StepNodeItem,
testées via un hit-test ici plutôt que via des QGraphicsItem enfants dédiés.
"""

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPen, QTransform
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsScene

from ui.styles import COLORS
from .node_item import StepNodeItem, PORT_RADIUS
from .edge_item import EdgeItem, TempEdgeItem
from .zone_item import ZoneItem

HIT_RADIUS = PORT_RADIUS + 6

# Guides d'alignement (chantier UX éditeur, Lot 3, A5) — seuil d'accrochage en coordonnées de
# scène, choix pragmatique sans spec utilisateur précise ; marge purement visuelle par laquelle
# un guide dépasse les rectangles qu'il relie, pour rester bien visible.
_SNAP_THRESHOLD = 6.0
_GUIDE_MARGIN = 40.0


def _find_snap(left: float, top: float, width: float, height: float,
                other_rects: list[tuple[float, float, float, float]],
                threshold: float = _SNAP_THRESHOLD):
    """Fonction pure, sans Qt : compare les lignes du rectangle glissé (gauche/centre/droite,
    haut/centre/bas) à celles de chaque `other_rect` = (left, top, width, height), retient par
    axe l'accord de distance minimale sous `threshold` (centres et bords traités à égalité —
    celui qui tombe le plus près l'emporte). Retourne (snap_left, snap_top, guide_x, guide_y) :
    snap_left/snap_top = position ajustée sur l'axe concerné (None si rien à portée) ;
    guide_x/guide_y = coordonnée de scène de la ligne d'accord elle-même, pour dessiner le
    guide — toujours défini exactement quand snap_left/snap_top l'est."""
    right, bottom = left + width, top + height
    cx, cy = left + width / 2, top + height / 2

    best_x = None   # (distance, snap_left, guide_x)
    best_y = None   # (distance, snap_top, guide_y)

    for o_left, o_top, o_w, o_h in other_rects:
        o_right, o_bottom = o_left + o_w, o_top + o_h
        o_cx, o_cy = o_left + o_w / 2, o_top + o_h / 2

        for my_x, o_x, offset in (
            (cx, o_cx, width / 2), (left, o_left, 0.0), (right, o_right, width),
            (left, o_right, 0.0), (right, o_left, width),
        ):
            d = abs(my_x - o_x)
            if d <= threshold and (best_x is None or d < best_x[0]):
                best_x = (d, o_x - offset, o_x)

        for my_y, o_y, offset in (
            (cy, o_cy, height / 2), (top, o_top, 0.0), (bottom, o_bottom, height),
            (top, o_bottom, 0.0), (bottom, o_top, height),
        ):
            d = abs(my_y - o_y)
            if d <= threshold and (best_y is None or d < best_y[0]):
                best_y = (d, o_y - offset, o_y)

    snap_left, guide_x = (best_x[1], best_x[2]) if best_x else (None, None)
    snap_top, guide_y = (best_y[1], best_y[2]) if best_y else (None, None)
    return snap_left, snap_top, guide_x, guide_y


class PipelineGraphScene(QGraphicsScene):
    node_double_clicked = Signal(object)   # StepNodeItem
    zone_double_clicked = Signal(object)   # ZoneItem — chantier UX éditeur, Lot 2, A4

    def __init__(self):
        super().__init__()
        self.nodes: dict[str, StepNodeItem] = {}   # step_key -> item
        self.edges: list[EdgeItem] = []
        self.zones: list[ZoneItem] = []             # chantier UX éditeur, Lot 2, A4
        self._pending_edge: TempEdgeItem | None = None
        self._pending_source: tuple[str, str] | None = None   # (step_key, port_name)
        self._executing_step_keys: set[str] = set()
        self._alignment_guides: list[QGraphicsLineItem] = []   # chantier UX éditeur, Lot 3, A5

    # ── Construction du graphe ────────────────

    def add_node(self, step: dict, pos: QPointF) -> StepNodeItem | None:
        key = (step.get("config") or {}).get("_step_key")
        if not key:
            return None
        node = StepNodeItem(step)
        node.setPos(pos)
        self.addItem(node)
        self.nodes[key] = node
        return node

    def add_zone(self, name: str, pos: QPointF, width: float = 240, height: float = 160) -> ZoneItem:
        zone = ZoneItem(name, width, height)
        zone.setPos(pos)
        self.addItem(zone)
        self.zones.append(zone)
        return zone

    def remove_zone(self, zone: ZoneItem) -> None:
        if zone in self.zones:
            self.zones.remove(zone)
        self.removeItem(zone)

    def add_edge(self, from_key: str, from_port: str, to_key: str) -> EdgeItem | None:
        if from_key == to_key:
            return None   # pas d'auto-boucle
        from_node = self.nodes.get(from_key)
        to_node   = self.nodes.get(to_key)
        if not from_node or not to_node:
            return None
        for e in self.edges:
            if e.from_node is from_node and e.from_port == from_port and e.to_node is to_node:
                return None   # doublon exact déjà présent
        edge = EdgeItem(from_node, from_port, to_node)
        self.addItem(edge)
        self.edges.append(edge)
        return edge

    def remove_node(self, node: StepNodeItem):
        for e in [e for e in self.edges if e.from_node is node or e.to_node is node]:
            self.remove_edge(e)
        key = node.step_key
        if key and self.nodes.get(key) is node:
            del self.nodes[key]
        self.removeItem(node)

    def remove_edge(self, edge: EdgeItem):
        if edge in self.edges:
            self.edges.remove(edge)
        self.removeItem(edge)

    def notify_node_moved(self, node: StepNodeItem):
        for e in self.edges:
            if e.from_node is node or e.to_node is node:
                e.update_path()

    # ── Guides d'alignement (chantier UX éditeur, Lot 3, A5) ────

    def snap_node_position(self, node: StepNodeItem, candidate_pos: QPointF) -> QPointF:
        """Appelé depuis StepNodeItem.itemChange() (ItemPositionChange) pendant un glissé
        interactif réel — jamais lors d'un setPos() programmatique (rangement, undo), voir
        StepNodeItem._dragging. Ajuste candidate_pos si un autre nœud est à portée de
        _SNAP_THRESHOLD sur un axe ou l'autre, affiche/masque les guides en conséquence."""
        other_rects = [
            (n.pos().x(), n.pos().y(), StepNodeItem.WIDTH, StepNodeItem.HEIGHT)
            for n in self.nodes.values() if n is not node
        ]
        snap_left, snap_top, guide_x, guide_y = _find_snap(
            candidate_pos.x(), candidate_pos.y(), StepNodeItem.WIDTH, StepNodeItem.HEIGHT,
            other_rects,
        )
        result_x = snap_left if snap_left is not None else candidate_pos.x()
        result_y = snap_top if snap_top is not None else candidate_pos.y()

        if guide_x is not None or guide_y is not None:
            self._show_alignment_guides(guide_x, guide_y, other_rects, result_x, result_y)
        else:
            self.clear_alignment_guides()

        return QPointF(result_x, result_y)

    def _show_alignment_guides(self, guide_x, guide_y, other_rects, node_left, node_top):
        while len(self._alignment_guides) < 2:
            line = QGraphicsLineItem()
            pen = QPen(QColor(COLORS["accent"]))
            pen.setStyle(Qt.DashLine)
            pen.setWidthF(1.5)
            line.setPen(pen)
            line.setZValue(5)
            self.addItem(line)
            self._alignment_guides.append(line)
        v_line, h_line = self._alignment_guides

        xs = [node_left, node_left + StepNodeItem.WIDTH]
        ys = [node_top, node_top + StepNodeItem.HEIGHT]
        for o_left, o_top, o_w, o_h in other_rects:
            xs += [o_left, o_left + o_w]
            ys += [o_top, o_top + o_h]

        if guide_x is not None:
            v_line.setLine(guide_x, min(ys) - _GUIDE_MARGIN, guide_x, max(ys) + _GUIDE_MARGIN)
        v_line.setVisible(guide_x is not None)

        if guide_y is not None:
            h_line.setLine(min(xs) - _GUIDE_MARGIN, guide_y, max(xs) + _GUIDE_MARGIN, guide_y)
        h_line.setVisible(guide_y is not None)

    def clear_alignment_guides(self) -> None:
        for line in self._alignment_guides:
            self.removeItem(line)
        self._alignment_guides = []

    def set_executing_step_keys(self, step_keys: set[str] | None) -> None:
        """Traçage lumineux (chantier identité visuelle, étendu au parallélisme intra-pipeline) :
        surligne TOUTES les étapes actuellement en cours d'une exécution réelle (nœud + ses
        arêtes entrantes, chacune) — un ensemble plutôt qu'une clé unique, pour qu'un run en
        mode parallèle puisse surligner plusieurs nœuds à la fois ; un run classique (une seule
        étape à la fois) n'y voit aucune différence, l'ensemble ne contient jamais qu'un élément.
        Appelé en continu par le QTimer de polling du dialogue — ne retouche que les nœuds dont
        l'état a réellement changé depuis le dernier appel."""
        step_keys = step_keys or set()
        if step_keys == self._executing_step_keys:
            return

        for key in self._executing_step_keys - step_keys:
            old_node = self.nodes.get(key)
            if old_node:
                old_node.set_executing(False)
                for e in self.edges:
                    if e.to_node is old_node:
                        e.set_executing(False)

        for key in step_keys - self._executing_step_keys:
            new_node = self.nodes.get(key)
            if new_node:
                new_node.set_executing(True)
                for e in self.edges:
                    if e.to_node is new_node:
                        e.set_executing(True)

        self._executing_step_keys = step_keys

    # ── Hit-test des ports ────────────────────

    def _port_at(self, scene_pos: QPointF):
        """Retourne (step_key, "input"|"output", port_name) si scene_pos tombe dans le rayon
        de tolérance d'un port, sinon None."""
        for key, node in self.nodes.items():
            if _within(scene_pos, node.input_port_pos()):
                return (key, "input", "input")
            for port in node.output_ports:
                if _within(scene_pos, node.output_port_pos(port)):
                    return (key, "output", port)
        return None

    # ── Drag-to-connect ───────────────────────

    def mousePressEvent(self, event):
        port = self._port_at(event.scenePos())
        if port and port[1] == "output":
            self._pending_source = (port[0], port[2])
            self._pending_edge = TempEdgeItem(self.nodes[port[0]].output_port_pos(port[2]))
            self.addItem(self._pending_edge)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pending_edge:
            self._pending_edge.update_end(event.scenePos())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.clear_alignment_guides()
        if self._pending_edge:
            port = self._port_at(event.scenePos())
            if port and port[1] == "input" and port[0] != self._pending_source[0]:
                self.add_edge(self._pending_source[0], self._pending_source[1], port[0])
            self.removeItem(self._pending_edge)
            self._pending_edge = None
            self._pending_source = None
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        item = self.itemAt(event.scenePos(), QTransform())
        if isinstance(item, StepNodeItem):
            self.node_double_clicked.emit(item)
            return
        if isinstance(item, ZoneItem):
            self.zone_double_clicked.emit(item)
            return
        super().mouseDoubleClickEvent(event)

    # ── Suppression ───────────────────────────

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            for item in list(self.selectedItems()):
                if isinstance(item, StepNodeItem):
                    self.remove_node(item)
                elif isinstance(item, EdgeItem):
                    self.remove_edge(item)
                elif isinstance(item, ZoneItem):
                    self.remove_zone(item)
            return
        super().keyPressEvent(event)


def _within(a: QPointF, b: QPointF, radius: float = HIT_RADIUS) -> bool:
    return (a - b).manhattanLength() <= radius * 2
