"""
DataScheduler — ui/graph_editor/zone_item.py
Zone de regroupement visuel (chantier UX éditeur, Lot 2, A4) : rectangle nommé qu'on peut
dessiner sur le canevas pour entourer visuellement un ensemble d'étapes (type "sous-processus"
Dataiku DSS / "frame" Miro-Figma) — purement décoratif, aucune référence d'étape, aucun impact
sur l'exécution.

Seule l'en-tête (bande du haut) déplace la zone — le corps reste "vide" au clic pour que la
sélection-rectangle (RubberBandDrag, déjà actif sur PipelineGraphView) continue de fonctionner
à l'intérieur, exactement comme dans les outils de référence cités ci-dessus. Sans cette
restriction, ItemIsMovable sur tout le rectangle capterait n'importe quel clic dans l'espace
"vide" que la zone est censée laisser sélectionnable.
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from ui.styles import COLORS

_HEADER_HEIGHT = 22.0
_HANDLE_SIZE = 10.0
_MIN_WIDTH = 80.0
_MIN_HEIGHT = 60.0


def _zone_header_rect(width: float) -> tuple[float, float, float, float]:
    """Bande du haut (x, y, w, h) — seule zone "prise" pour déplacer la zone."""
    return (0.0, 0.0, width, _HEADER_HEIGHT)


def _zone_handle_rect(width: float, height: float) -> tuple[float, float, float, float]:
    """Poignée de redimensionnement (x, y, w, h) — coin bas-droit uniquement."""
    return (width - _HANDLE_SIZE, height - _HANDLE_SIZE, _HANDLE_SIZE, _HANDLE_SIZE)


def _clamp_zone_size(w: float, h: float,
                      min_w: float = _MIN_WIDTH, min_h: float = _MIN_HEIGHT) -> tuple[float, float]:
    return (max(w, min_w), max(h, min_h))


class ZoneItem(QGraphicsObject):
    def __init__(self, name: str, width: float = 240, height: float = 160):
        super().__init__()
        self.name = name
        self._width = float(width)
        self._height = float(height)
        self._resizing = False
        self._resize_start_mouse = None
        self._resize_start_size = None
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        # Sous les nœuds (StepNodeItem, z=1) et sous les arêtes (EdgeItem, z=0, explicite) —
        # se lit comme un fond de regroupement, jamais au-dessus du contenu qu'elle entoure.
        self.setZValue(-1)

    # ── Qt ────────────────────────────────────

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._width, self._height)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)

        body = QColor(COLORS["bg_hover"]); body.setAlpha(90)
        border_color = QColor(COLORS["border"])
        painter.setPen(QPen(border_color, 1.5))
        painter.setBrush(QBrush(body))
        painter.drawRect(QRectF(0, 0, self._width, self._height))

        hx, hy, hw, hh = _zone_header_rect(self._width)
        header = QColor(COLORS["bg_panel"]); header.setAlpha(180)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(header))
        painter.drawRect(QRectF(hx, hy, hw, hh))

        painter.setPen(QColor(COLORS["text_dim"]))
        font = QFont(); font.setBold(True); font.setPointSize(8)
        painter.setFont(font)
        painter.drawText(QRectF(hx + 6, hy, hw - 12, hh), Qt.AlignLeft | Qt.AlignVCenter, self.name)

        gx, gy, gw, gh = _zone_handle_rect(self._width, self._height)
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(QBrush(QColor(COLORS["text_dim"])))
        painter.drawRect(QRectF(gx, gy, gw, gh))

    def mousePressEvent(self, event):
        pos = event.pos()
        hx, hy, hw, hh = _zone_handle_rect(self._width, self._height)
        if QRectF(hx, hy, hw, hh).contains(pos):
            self._resizing = True
            self._resize_start_mouse = event.scenePos()
            self._resize_start_size = (self._width, self._height)
            event.accept()
            return

        hx2, hy2, hw2, hh2 = _zone_header_rect(self._width)
        if QRectF(hx2, hy2, hw2, hh2).contains(pos):
            super().mousePressEvent(event)
            return

        # Clic dans le corps "vide" de la zone — jamais accepté ici, pour que Qt le propage à
        # l'item en dessous ou, s'il n'y en a pas, au fond de la scène (sélection-rectangle).
        event.ignore()

    def mouseMoveEvent(self, event):
        if self._resizing:
            delta = event.scenePos() - self._resize_start_mouse
            new_w = self._resize_start_size[0] + delta.x()
            new_h = self._resize_start_size[1] + delta.y()
            new_w, new_h = _clamp_zone_size(new_w, new_h)
            self.prepareGeometryChange()
            self._width, self._height = new_w, new_h
            self.update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            event.accept()
            return
        super().mouseReleaseEvent(event)
