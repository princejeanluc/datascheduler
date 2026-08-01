"""
DataScheduler — ui/main_window/activity_chart.py
Widget de graphique "fait maison" (QPainter) pour l'activité du Dashboard — barres empilées
succès/échec/annulé par jour. Zéro nouvelle dépendance (pas de QtCharts/pyqtgraph) — décision
actée avec l'utilisateur : ce projet a déjà été mordu plusieurs fois par des hiddenimports
PyInstaller manquants (pynacl, oracledb.impl, keyring), et le besoin (barres empilées, ~30
points) ne justifie pas une bibliothèque de charts complète.
"""

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from PySide6.QtWidgets import QWidget, QToolTip

from ui.styles import COLORS

_BAR_GAP       = 3
_MARGIN_LEFT   = 8
_MARGIN_RIGHT  = 8
_MARGIN_TOP    = 12
_MARGIN_BOTTOM = 22


class ActivityChartWidget(QWidget):
    """
    Barres empilées succès/échec/annulé, une par jour. `set_data` accepte directement la sortie
    de `db_manager.get_run_counts_by_day()` (une entrée par jour, la plus ancienne en premier,
    zéro-remplie pour les jours sans exécution). Le calcul de géométrie (`_bar_rect`,
    `_bar_index_at`) est séparé du rendu pour rester testable sans dépendre du pixel — même
    logique appelée par `paintEvent` et par `mouseMoveEvent` pour le survol.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[dict] = []
        self._max_total = 1
        self.setMinimumHeight(100)
        self.setMouseTracking(True)

    def set_data(self, daily_counts: list[dict]) -> None:
        self._data = daily_counts
        self._max_total = max(
            (d["success"] + d["failed"] + d["cancelled"] for d in daily_counts), default=0
        ) or 1
        self.update()

    # ── Géométrie (partagée rendu / survol) ───────

    def _plot_rect(self) -> QRectF:
        return QRectF(
            _MARGIN_LEFT, _MARGIN_TOP,
            max(0.0, self.width() - _MARGIN_LEFT - _MARGIN_RIGHT),
            max(0.0, self.height() - _MARGIN_TOP - _MARGIN_BOTTOM),
        )

    def _bar_rect(self, index: int) -> QRectF:
        """Rectangle englobant (toute la hauteur du tracé) de la barre du jour `index`."""
        plot = self._plot_rect()
        n = len(self._data)
        if n == 0:
            return QRectF()
        bar_w = plot.width() / n
        x = plot.left() + index * bar_w
        return QRectF(x + _BAR_GAP / 2, plot.top(), max(1.0, bar_w - _BAR_GAP), plot.height())

    def _bar_index_at(self, pos: QPointF):
        plot = self._plot_rect()
        if not self._data or plot.width() <= 0 or not plot.contains(pos):
            return None
        n = len(self._data)
        bar_w = plot.width() / n
        idx = int((pos.x() - plot.left()) // bar_w)
        return idx if 0 <= idx < n else None

    # ── Rendu ──────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        plot = self._plot_rect()

        grid_pen = QPen(QColor(COLORS["border"]))
        grid_pen.setWidthF(1)
        painter.setPen(grid_pen)
        for frac in (0.0, 0.5, 1.0):
            y = plot.bottom() - frac * plot.height()
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

        if not self._data:
            painter.setPen(QColor(COLORS["text_muted"]))
            painter.drawText(self.rect(), Qt.AlignCenter, "Aucune exécution enregistrée")
            painter.end()
            return

        for i, day in enumerate(self._data):
            rect = self._bar_rect(i)
            self._paint_stacked_bar(painter, rect, day, emphasized=(i == len(self._data) - 1))

        painter.setPen(QColor(COLORS["text_muted"]))
        painter.setFont(QFont("Segoe UI", 9))
        first_rect = self._bar_rect(0)
        last_rect  = self._bar_rect(len(self._data) - 1)
        painter.drawText(
            QRectF(first_rect.left(), plot.bottom() + 4, 100, 16),
            Qt.AlignLeft, self._data[0]["date"].strftime("%d/%m"),
        )
        painter.drawText(
            QRectF(last_rect.right() - 100, plot.bottom() + 4, 100, 16),
            Qt.AlignRight, self._data[-1]["date"].strftime("%d/%m"),
        )
        painter.end()

    def _paint_stacked_bar(self, painter: QPainter, rect: QRectF, day: dict, emphasized: bool):
        total = day["success"] + day["failed"] + day["cancelled"]
        if total == 0:
            return
        scale = rect.height() / self._max_total
        segments = [
            (day["success"],   COLORS["success"]),
            (day["failed"],    COLORS["danger"]),
            (day["cancelled"], COLORS["text_dim"]),
        ]
        y = rect.bottom()
        for count, color in segments:
            if count <= 0:
                continue
            h = count * scale
            qcolor = QColor(color)
            if not emphasized:
                qcolor.setAlpha(210)
            painter.fillRect(QRectF(rect.left(), y - h, rect.width(), h), qcolor)
            y -= h

    # ── Survol ─────────────────────────────────────

    def mouseMoveEvent(self, event):
        idx = self._bar_index_at(event.position())
        if idx is None:
            QToolTip.hideText()
            return super().mouseMoveEvent(event)
        day = self._data[idx]
        total = day["success"] + day["failed"] + day["cancelled"]
        text = (
            f"{day['date'].strftime('%d/%m/%Y')} — {total} exécution(s)\n"
            f"Succès : {day['success']}   Échecs : {day['failed']}   Annulés : {day['cancelled']}"
        )
        QToolTip.showText(event.globalPosition().toPoint(), text, self)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)
