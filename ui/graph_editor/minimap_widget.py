"""
DataScheduler — ui/graph_editor/minimap_widget.py
Mini-carte de navigation du canevas (chantier UX éditeur, Lot 2, A3) : vignette d'ensemble du
graphe + rectangle de la zone actuellement visible, cliquable/glissable pour recentrer la vue —
premier composant du genre dans cette app, aucun précédent de superposition sur un
QGraphicsView ailleurs dans le code.

Les fonctions de mapping ci-dessous sont volontairement pures (tuples (x, y, w, h)/(x, y), pas de
QRectF/QPointF) — même discipline que _diamond_port_local_pos()/_port_visual() dans node_item.py,
pour rester testables sans peindre réellement ni instancier QApplication.
"""

from PySide6.QtCore import QRectF, QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ui.styles import COLORS

_MARGIN_TO_PARENT = 8
_INNER_MARGIN = 2
_REPAINT_DEBOUNCE_MS = 80


def _minimap_target_rect(width: float, height: float,
                          margin: float = _INNER_MARGIN) -> tuple[float, float, float, float]:
    """Rectangle interne (x, y, w, h) où la scène est rendue, en retrait du cadre du widget."""
    return (margin, margin, max(width - 2 * margin, 1.0), max(height - 2 * margin, 1.0))


def _scene_point_to_minimap(sx: float, sy: float,
                             source: tuple[float, float, float, float],
                             target: tuple[float, float, float, float]) -> tuple[float, float]:
    src_x, src_y, src_w, src_h = source
    tgt_x, tgt_y, tgt_w, tgt_h = target
    if src_w <= 0 or src_h <= 0:
        return (tgt_x, tgt_y)
    scale_x = tgt_w / src_w
    scale_y = tgt_h / src_h
    return (tgt_x + (sx - src_x) * scale_x, tgt_y + (sy - src_y) * scale_y)


def _scene_rect_to_minimap(rect: tuple[float, float, float, float],
                            source: tuple[float, float, float, float],
                            target: tuple[float, float, float, float]
                            ) -> tuple[float, float, float, float]:
    rx, ry, rw, rh = rect
    x0, y0 = _scene_point_to_minimap(rx, ry, source, target)
    x1, y1 = _scene_point_to_minimap(rx + rw, ry + rh, source, target)
    return (x0, y0, x1 - x0, y1 - y0)


def _minimap_point_to_scene(mx: float, my: float,
                             source: tuple[float, float, float, float],
                             target: tuple[float, float, float, float]
                             ) -> tuple[float, float] | None:
    """None si la scène est vide ou le rectangle cible dégénéré — pas de point de scène sensé."""
    src_x, src_y, src_w, src_h = source
    tgt_x, tgt_y, tgt_w, tgt_h = target
    if src_w <= 0 or src_h <= 0 or tgt_w <= 0 or tgt_h <= 0:
        return None
    scale_x = src_w / tgt_w
    scale_y = src_h / tgt_h
    return (src_x + (mx - tgt_x) * scale_x, src_y + (my - tgt_y) * scale_y)


class GraphMinimapWidget(QWidget):
    WIDTH, HEIGHT = 180, 130

    def __init__(self, scene, view, parent=None):
        super().__init__(parent)
        self._scene = scene
        self._view = view
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self._dragging = False

        # Anti-rebond du repeint (chantier UX éditeur, Lot 2) : QGraphicsScene.changed() se
        # déclenche très fréquemment (plusieurs fois par glissé de nœud) — un scene.render() à
        # chaque tick ferait ramer le canevas. Même idiome que le QTimer de traçage lumineux
        # déjà existant (self._executing_timer, graph_editor_dialog.py) : on ne repeint qu'à
        # l'expiration d'un minuteur redémarré à chaque signal source, jamais sur le signal brut
        # directement.
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_REPAINT_DEBOUNCE_MS)
        self._debounce.timeout.connect(self.update)

    def request_repaint(self) -> None:
        self._debounce.start()

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        x = parent.width() - self.width() - _MARGIN_TO_PARENT
        y = parent.height() - self.height() - _MARGIN_TO_PARENT
        self.move(max(0, x), max(0, y))

    def _rects(self):
        source_rect = self._scene.itemsBoundingRect()
        source = (source_rect.x(), source_rect.y(), source_rect.width(), source_rect.height())
        target = _minimap_target_rect(self.width(), self.height())
        return source_rect, source, target

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(COLORS["bg_panel"]))
        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        source_rect, source, target = self._rects()
        if source_rect.isEmpty():
            # Pipeline sans étape (ou toutes supprimées) — rien à rendre, évite une division
            # par zéro dans le calcul du facteur d'échelle.
            return

        self._scene.render(painter, QRectF(*target), source_rect)

        viewport_rect = self._view.mapToScene(self._view.viewport().rect()).boundingRect()
        vx, vy, vw, vh = _scene_rect_to_minimap(
            (viewport_rect.x(), viewport_rect.y(), viewport_rect.width(), viewport_rect.height()),
            source, target,
        )
        painter.setPen(QPen(QColor(COLORS["accent"]), 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(vx, vy, vw, vh))

    def mousePressEvent(self, event):
        self._dragging = True
        self._navigate(event.position())

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._navigate(event.position())

    def mouseReleaseEvent(self, event):
        self._dragging = False

    def _navigate(self, widget_pos) -> None:
        _, source, target = self._rects()
        scene_point = _minimap_point_to_scene(widget_pos.x(), widget_pos.y(), source, target)
        if scene_point is not None:
            self._view.centerOn(QPointF(*scene_point))
