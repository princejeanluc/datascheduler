"""
DataScheduler — ui/graph_editor/node_item.py
Nœud du canevas : représente une étape (dict complet step_type/label/config/retry_count/
run_always) — le même objet que celui retourné par _open_config_dialog(...).result_step().
"""

from PySide6.QtCore import QPointF, QRectF, Qt, QSize
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from ui.styles import COLORS
from ui.step_editor import STEP_META
from ui.step_editor.common import _icon
from core.steps import get_step_output_ports

PORT_RADIUS = 6


class StepNodeItem(QGraphicsObject):
    """
    Rectangle arrondi représentant une étape sur le canevas. Porte le dict `step` complet —
    aucune génération de `_step_key` ici, il vient gratuitement de
    `_open_config_dialog(...).result_step()` (chantier 3), réutilisé tel quel pour créer/éditer
    la configuration d'un nœud.
    """

    WIDTH, HEIGHT = 200, 64

    def __init__(self, step: dict):
        super().__init__()
        self.step = step
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(1)

    # ── Identité ──────────────────────────────

    @property
    def step_key(self) -> str | None:
        return (self.step.get("config") or {}).get("_step_key")

    @property
    def output_ports(self) -> tuple[str, ...]:
        return get_step_output_ports(self.step.get("step_type", ""))

    # ── Géométrie des ports (coordonnées de scène) ──

    def input_port_pos(self) -> QPointF:
        return self.mapToScene(QPointF(0, self.HEIGHT / 2))

    def output_port_pos(self, port: str) -> QPointF:
        ports = self.output_ports
        if len(ports) <= 1:
            y = self.HEIGHT / 2
        else:
            idx = ports.index(port) if port in ports else 0
            step = self.HEIGHT / (len(ports) + 1)
            y = step * (idx + 1)
        return self.mapToScene(QPointF(self.WIDTH, y))

    # ── Qt ────────────────────────────────────

    def boundingRect(self) -> QRectF:
        return QRectF(-PORT_RADIUS, -PORT_RADIUS,
                      self.WIDTH + 2 * PORT_RADIUS, self.HEIGHT + 2 * PORT_RADIUS)

    def paint(self, painter, option, widget=None):
        step_type = self.step.get("step_type", "")
        meta = STEP_META.get(step_type, {"label": step_type, "color": COLORS["accent"]})

        rect = QRectF(0, 0, self.WIDTH, self.HEIGHT)
        path = QPainterPath()
        path.addRoundedRect(rect, 8, 8)

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor(COLORS["bg_card"])))
        border_color = QColor(meta["color"])
        pen = QPen(border_color, 3 if self.isSelected() else 1.5)
        painter.setPen(pen)
        painter.drawPath(path)

        painter.setPen(QColor(meta["color"]))
        font = QFont(); font.setBold(True); font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(QRectF(10, 6, self.WIDTH - 40, 18), Qt.AlignLeft | Qt.AlignVCenter,
                          meta["label"])

        type_icon = _icon(meta.get("icon", "fa5s.circle"), meta["color"])
        if type_icon:
            painter.drawPixmap(self.WIDTH - 24, 6, type_icon.pixmap(QSize(16, 16)))

        user_label = self.step.get("label") or ""
        if user_label:
            painter.setPen(QColor(COLORS["text_main"]))
            font.setBold(False); font.setPointSize(8)
            painter.setFont(font)
            painter.drawText(QRectF(10, 26, self.WIDTH - 20, 18), Qt.AlignLeft | Qt.AlignVCenter,
                              user_label)

        # Port d'entrée (toujours dessiné, connecté ou non).
        painter.setBrush(QBrush(QColor(COLORS["text_dim"])))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(0, self.HEIGHT / 2), PORT_RADIUS, PORT_RADIUS)

        # Port(s) de sortie.
        ports = self.output_ports
        for i, port in enumerate(ports):
            if len(ports) <= 1:
                y = self.HEIGHT / 2
                color = COLORS["text_dim"]
            else:
                step = self.HEIGHT / (len(ports) + 1)
                y = step * (i + 1)
                color = COLORS["success"] if port == "true" else COLORS["danger"]
            painter.setBrush(QBrush(QColor(color)))
            painter.drawEllipse(QPointF(self.WIDTH, y), PORT_RADIUS, PORT_RADIUS)
            if len(ports) > 1:
                painter.setPen(QColor(color))
                label = "V" if port == "true" else "F"
                painter.drawText(QRectF(self.WIDTH - 22, y - 9, 16, 18),
                                  Qt.AlignRight | Qt.AlignVCenter, label)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            self.scene().notify_node_moved(self)
        return super().itemChange(change, value)
