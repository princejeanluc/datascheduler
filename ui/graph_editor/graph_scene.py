"""
DataScheduler — ui/graph_editor/graph_scene.py
Scène du canevas : centralise l'état d'interaction (drag-to-connect, suppression). Pas de classe
PortItem séparée — les ports sont de petites zones de tolérance calculées sur StepNodeItem,
testées via un hit-test ici plutôt que via des QGraphicsItem enfants dédiés.
"""

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QTransform
from PySide6.QtWidgets import QGraphicsScene

from .node_item import StepNodeItem, PORT_RADIUS
from .edge_item import EdgeItem, TempEdgeItem

HIT_RADIUS = PORT_RADIUS + 6


class PipelineGraphScene(QGraphicsScene):
    node_double_clicked = Signal(object)   # StepNodeItem

    def __init__(self):
        super().__init__()
        self.nodes: dict[str, StepNodeItem] = {}   # step_key -> item
        self.edges: list[EdgeItem] = []
        self._pending_edge: TempEdgeItem | None = None
        self._pending_source: tuple[str, str] | None = None   # (step_key, port_name)
        self._executing_step_key: str | None = None

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

    def set_executing_step_key(self, step_key: str | None) -> None:
        """Traçage lumineux (chantier identité visuelle) : surligne l'étape en cours d'une
        exécution réelle (nœud + ses arêtes entrantes), retire le surlignage précédent le cas
        échéant. Appelé en continu par le QTimer de polling du dialogue — no-op si l'étape en
        cours n'a pas changé depuis le dernier appel."""
        if step_key == self._executing_step_key:
            return
        old_node = self.nodes.get(self._executing_step_key) if self._executing_step_key else None
        if old_node:
            old_node.set_executing(False)
            for e in self.edges:
                if e.to_node is old_node:
                    e.set_executing(False)

        self._executing_step_key = step_key
        new_node = self.nodes.get(step_key) if step_key else None
        if new_node:
            new_node.set_executing(True)
            for e in self.edges:
                if e.to_node is new_node:
                    e.set_executing(True)

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
        super().mouseDoubleClickEvent(event)

    # ── Suppression ───────────────────────────

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            for item in list(self.selectedItems()):
                if isinstance(item, StepNodeItem):
                    self.remove_node(item)
                elif isinstance(item, EdgeItem):
                    self.remove_edge(item)
            return
        super().keyPressEvent(event)


def _within(a: QPointF, b: QPointF, radius: float = HIT_RADIUS) -> bool:
    return (a - b).manhattanLength() <= radius * 2
