"""
DataScheduler — ui/main_window/resources_view.py
Vue Ressources (chantier suivi des ressources) : CPU/mémoire agrégés de l'application dans le
temps, mis en regard du nombre de pipelines en cours — jamais une mesure par pipeline (ils
tournent en threads dans le même process, impossible à attribuer proprement). Le survol d'un
point liste les pipelines réellement actifs à cet instant (déduits de PipelineRun.started_at/
finished_at, pas une nouvelle mesure) : c'est à l'utilisateur de faire le lien entre une pointe
de CPU et une salve de pipelines, pas à l'appli de l'inventer.

Maquette validée avec l'utilisateur avant implémentation — mêmes 3 graphiques empilés partageant
un axe temporel (jamais un seul graphique à deux échelles), curseur synchronisé, panneau de
corrélation en pastilles.
"""

from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame, QScrollArea,
)
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QFont

from ui.styles import COLORS, FONT_MONO
from .widgets import _make_title, _make_subtitle, StatCard

# Hues catégorielles validées (kit dataviz — CVD/contraste/luminosité, --pairs all en dark) —
# distinctes de COLORS['accent']/['signal'] (identité de marque/nav), jamais réutilisées pour
# une série de données (voir la maquette validée).
_COLOR_CPU   = "#3987e5"
_COLOR_RAM   = "#199e70"
_COLOR_COUNT = "#d95926"

_RANGES = [("1h", 1), ("6h", 6), ("24h", 24), ("7j", 24 * 7)]

_HINT_HOVER = "Survolez un graphique pour voir le détail d'un instant."
_HINT_NO_PIPELINE = "Aucun pipeline en cours à cet instant."

_MARGIN_LEFT, _MARGIN_RIGHT, _MARGIN_TOP, _MARGIN_BOTTOM = 4, 4, 6, 6


class _TimeSeriesChart(QWidget):
    """Une série, aire lissée + ligne — même famille qu'ActivityChartWidget (géométrie séparée
    du paintEvent, testable sans dépendre du pixel). N'affiche qu'UNE série (jamais un second
    axe) : pour comparer CPU/mémoire/pipelines, on empile 3 instances plutôt que d'en combiner
    deux dans un même graphique à deux échelles.

    hovered/hover_left permettent à un widget parent de synchroniser le curseur sur plusieurs
    instances en même temps (voir ResourcesView._on_chart_hover)."""

    hovered    = Signal(int)
    hover_left = Signal()

    def __init__(self, color: str, max_value: float | None = None, parent=None):
        super().__init__(parent)
        self._values: list[float] = []
        self._color = color
        self._fixed_max = max_value
        self._crosshair_index: int | None = None
        self.setMinimumHeight(70)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)

    def set_data(self, values: list[float]) -> None:
        self._values = values
        self.update()

    def set_crosshair(self, index: int | None) -> None:
        if index != self._crosshair_index:
            self._crosshair_index = index
            self.update()

    # ── Géométrie (partagée rendu / survol) ───────

    def _plot_rect(self) -> QRectF:
        return QRectF(
            _MARGIN_LEFT, _MARGIN_TOP,
            max(0.0, self.width() - _MARGIN_LEFT - _MARGIN_RIGHT),
            max(0.0, self.height() - _MARGIN_TOP - _MARGIN_BOTTOM),
        )

    def _max_value(self) -> float:
        if self._fixed_max is not None:
            return self._fixed_max
        return max(self._values, default=1) * 1.15 or 1

    def _point_at(self, index: int) -> QPointF:
        plot = self._plot_rect()
        n = len(self._values)
        x = plot.left() if n <= 1 else plot.left() + (index / (n - 1)) * plot.width()
        v = self._values[index]
        y = plot.bottom() - (v / self._max_value()) * plot.height()
        return QPointF(x, y)

    def _index_at_x(self, x: float):
        plot = self._plot_rect()
        n = len(self._values)
        if n == 0 or plot.width() <= 0:
            return None
        ratio = (x - plot.left()) / plot.width()
        idx = round(ratio * (n - 1))
        return max(0, min(n - 1, idx))

    # ── Rendu ──────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        plot = self._plot_rect()

        grid_pen = QPen(QColor(COLORS["border"])); grid_pen.setWidthF(1)
        painter.setPen(grid_pen)
        painter.drawLine(QPointF(plot.left(), plot.bottom()), QPointF(plot.right(), plot.bottom()))

        if len(self._values) >= 2:
            points = [self._point_at(i) for i in range(len(self._values))]
            line_path = _smooth_path(points)
            area_path = QPainterPath(line_path)
            area_path.lineTo(plot.right(), plot.bottom())
            area_path.lineTo(plot.left(), plot.bottom())
            area_path.closeSubpath()

            fill_color = QColor(self._color); fill_color.setAlphaF(0.12)
            painter.fillPath(area_path, fill_color)

            line_pen = QPen(QColor(self._color), 2)
            line_pen.setCapStyle(Qt.RoundCap); line_pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(line_pen)
            painter.drawPath(line_path)

        if self._crosshair_index is not None and self._values:
            idx = max(0, min(len(self._values) - 1, self._crosshair_index))
            pt = self._point_at(idx)
            cross_pen = QPen(QColor(COLORS["text_dim"]), 1)
            painter.setPen(cross_pen)
            painter.drawLine(QPointF(pt.x(), plot.top()), QPointF(pt.x(), plot.bottom()))
            painter.setPen(QPen(QColor(COLORS["bg_card"]), 2))
            painter.setBrush(QColor(self._color))
            painter.drawEllipse(pt, 4, 4)

        painter.end()

    # ── Survol ─────────────────────────────────────

    def mouseMoveEvent(self, event):
        idx = self._index_at_x(event.position().x())
        if idx is not None:
            self.hovered.emit(idx)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hover_left.emit()
        super().leaveEvent(event)


def _smooth_path(points: list[QPointF]) -> QPainterPath:
    """Courbe lissée par des Bézier cubiques (approximation Catmull-Rom), même technique que la
    maquette HTML validée — traduite ici en QPainterPath plutôt qu'en chemin SVG."""
    path = QPainterPath(points[0])
    n = len(points)
    for i in range(n - 1):
        p0 = points[i - 1] if i > 0 else points[0]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[i + 2] if i + 2 < n else points[i + 1]
        c1 = QPointF(p1.x() + (p2.x() - p0.x()) / 6, p1.y() + (p2.y() - p0.y()) / 6)
        c2 = QPointF(p2.x() - (p3.x() - p1.x()) / 6, p2.y() - (p3.y() - p1.y()) / 6)
        path.cubicTo(c1, c2, p2)
    return path


class ResourcesView(QWidget):
    def __init__(self):
        super().__init__()
        self._range_hours = 24
        self._samples: list = []
        self._runs: list = []
        self._build_ui()
        from database import db_manager as db
        self._timer = QTimer(self)
        self._timer.setInterval(db.get_app_settings().resource_sample_interval_s * 1000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    # ── Construction ──────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(32, 24, 32, 4)
        title_col = QVBoxLayout(); title_col.setSpacing(2)
        title_col.addWidget(_make_title("Ressources"))
        title_col.addWidget(_make_subtitle(
            "Utilisation de l'application dans le temps — de quoi repérer une corrélation avec "
            "vos pipelines, pas une mesure isolée par pipeline (impossible : ils partagent le "
            "même processus)."
        ))
        header.addLayout(title_col)
        header.addStretch()

        self._range_buttons = {}
        for label, hours in _RANGES:
            btn = QPushButton(label)
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda _, h=hours: self._on_range_changed(h))
            header.addWidget(btn)
            self._range_buttons[hours] = btn

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        content = QWidget()
        scroll.setWidget(content)

        body = QVBoxLayout(content)
        body.setContentsMargins(32, 20, 32, 32)
        body.setSpacing(20)

        stats_row = QHBoxLayout(); stats_row.setSpacing(14)
        self._card_running   = StatCard("En cours", "—")
        self._card_peak_cpu  = StatCard("Pic CPU (fenêtre)", "—")
        self._card_memory    = StatCard("Mémoire actuelle", "—")
        self._card_samples   = StatCard("Échantillons", "—")
        for card in (self._card_running, self._card_peak_cpu, self._card_memory, self._card_samples):
            stats_row.addWidget(card)
        body.addLayout(stats_row)

        charts_frame = QFrame(); charts_frame.setObjectName("card")
        charts_layout = QVBoxLayout(charts_frame)
        charts_layout.setContentsMargins(20, 18, 20, 10)
        charts_layout.setSpacing(4)

        self._chart_cpu = _TimeSeriesChart(_COLOR_CPU, max_value=100)
        self._chart_ram = _TimeSeriesChart(_COLOR_RAM)
        self._chart_count = _TimeSeriesChart(_COLOR_COUNT)
        self._charts = [self._chart_cpu, self._chart_ram, self._chart_count]

        charts_layout.addWidget(self._chart_title_row("Utilisation CPU (%)", _COLOR_CPU, "latest_cpu"))
        charts_layout.addWidget(self._chart_cpu)
        charts_layout.addWidget(self._chart_title_row("Mémoire (Mo)", _COLOR_RAM, "latest_ram"))
        charts_layout.addWidget(self._chart_ram)
        charts_layout.addWidget(self._chart_title_row("Pipelines en cours", _COLOR_COUNT, "latest_count"))
        charts_layout.addWidget(self._chart_count)

        for chart in self._charts:
            chart.hovered.connect(self._on_chart_hover)
            chart.hover_left.connect(self._on_chart_hover_left)

        body.addWidget(charts_frame)

        correlate_title = QLabel("Pipelines actifs à l'instant survolé")
        correlate_title.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {COLORS['text_main']};")
        body.addWidget(correlate_title)
        correlate_sub = QLabel(
            "Survolez un point des graphiques ci-dessus pour voir précisément quels pipelines "
            "tournaient à ce moment."
        )
        correlate_sub.setWordWrap(True)
        correlate_sub.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11.5px;")
        body.addWidget(correlate_sub)

        # Widgets construits UNE SEULE FOIS et toujours gardés dans le layout, jamais retirés/
        # recréés — seule leur visibilité/texte change. Un précédent essai qui les ré-ajoutait
        # via addWidget() après les avoir fait passer par une boucle "vider le layout" (deleteLater
        # sur tout ce qui s'y trouvait) finissait par supprimer _correlate_empty lui-même dès
        # qu'il se trouvait déjà dans le layout au moment du nettoyage suivant — crash confirmé
        # en usage réel ("Internal C++ object already deleted"). Seuls les chips (nombre variable,
        # eux vraiment jetables) sont recréés à chaque survol, dans leur propre sous-layout dédié.
        self._correlate_panel = QFrame(); self._correlate_panel.setObjectName("card")
        self._correlate_layout = QVBoxLayout(self._correlate_panel)
        self._correlate_layout.setContentsMargins(16, 16, 16, 16)
        self._correlate_layout.setSpacing(8)

        self._correlate_time_lbl = QLabel("")
        self._correlate_time_lbl.setStyleSheet(
            f"color: {COLORS['signal_pale']}; font-family: {FONT_MONO}; font-size: 12px;")
        self._correlate_time_lbl.setVisible(False)
        self._correlate_layout.addWidget(self._correlate_time_lbl)

        self._correlate_empty = QLabel(_HINT_HOVER)
        self._correlate_empty.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px; font-style: italic;")
        self._correlate_layout.addWidget(self._correlate_empty)

        self._correlate_chips = QWidget()
        self._correlate_chips_layout = QHBoxLayout(self._correlate_chips)
        self._correlate_chips_layout.setContentsMargins(0, 0, 0, 0)
        self._correlate_chips_layout.setSpacing(8)
        self._correlate_chips.setVisible(False)
        self._correlate_layout.addWidget(self._correlate_chips)

        body.addWidget(self._correlate_panel)

        outer.addLayout(header)
        outer.addWidget(scroll, stretch=1)

        self._set_active_range(24)

    def _chart_title_row(self, text: str, color: str, latest_attr: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(8)
        key = QLabel(); key.setFixedSize(10, 3)
        key.setStyleSheet(f"background: {color}; border-radius: 1px;")
        layout.addWidget(key)
        label = QLabel(text)
        label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11.5px; font-weight: 600;")
        layout.addWidget(label)
        layout.addStretch()
        latest = QLabel("")
        latest.setStyleSheet(f"color: {COLORS['text_main']}; font-family: {FONT_MONO}; font-size: 12px;")
        layout.addWidget(latest)
        setattr(self, f"_lbl_{latest_attr}", latest)
        return row

    # ── Plage temporelle ───────────────────────

    def _on_range_changed(self, hours: int):
        self._set_active_range(hours)
        self.refresh()

    def _set_active_range(self, hours: int):
        self._range_hours = hours
        for h, btn in self._range_buttons.items():
            active = h == hours
            btn.setStyleSheet(
                f"QPushButton {{ border-radius: 15px; padding: 0 14px; font-size: 12px; "
                f"font-weight: {'700' if active else '500'}; "
                f"background: {COLORS['bg_active'] if active else 'transparent'}; "
                f"color: {COLORS['text_main'] if active else COLORS['text_dim']}; "
                f"border: 1px solid {COLORS['accent'] if active else COLORS['border']}; }}"
                f"QPushButton:hover {{ border-color: {COLORS['accent']}; color: {COLORS['text_main']}; }}"
            )

    # ── Données ────────────────────────────────

    def refresh(self):
        from database import db_manager as db
        import core.pipeline as pipeline_module

        since = datetime.utcnow() - timedelta(hours=self._range_hours)
        self._samples = db.get_resource_samples(since)
        self._runs = db.get_runs_overlapping_window(since, datetime.utcnow())

        cpu_values = [s.cpu_percent for s in self._samples]
        ram_values = [s.memory_mb for s in self._samples]
        count_values = [self._running_count_at(s.timestamp) for s in self._samples]

        self._chart_cpu.set_data(cpu_values)
        self._chart_ram.set_data(ram_values)
        self._chart_count.set_data(count_values)

        self._lbl_latest_cpu.setText(f"{cpu_values[-1]:.0f} %" if cpu_values else "—")
        self._lbl_latest_ram.setText(f"{ram_values[-1]:.0f} Mo" if ram_values else "—")
        self._lbl_latest_count.setText(f"{count_values[-1]} en cours" if count_values else "—")

        # Lecture seule d'un int (len() sur un dict) — pas besoin du verrou réel de
        # core.pipeline._active_runs_lock, juste utilisé ici pour affichage.
        running_now = len(pipeline_module._active_runs)
        max_concurrent = db.get_app_settings().max_concurrent_runs
        self._card_running.set_value(f"{running_now} / {max_concurrent}")
        self._card_peak_cpu.set_value(f"{max(cpu_values, default=0):.0f} %")
        self._card_memory.set_value(f"{ram_values[-1]:.0f} Mo" if ram_values else "—")
        self._card_samples.set_value(str(len(self._samples)))

    def _running_count_at(self, instant: datetime) -> int:
        return sum(
            1 for r in self._runs
            if r.started_at and r.started_at <= instant
            and (r.finished_at is None or r.finished_at >= instant)
        )

    def _runs_active_at(self, instant: datetime) -> list:
        return [
            r for r in self._runs
            if r.started_at and r.started_at <= instant
            and (r.finished_at is None or r.finished_at >= instant)
        ]

    # ── Curseur synchronisé + panneau de corrélation ──

    def _on_chart_hover(self, index: int):
        for chart in self._charts:
            chart.set_crosshair(index)
        if 0 <= index < len(self._samples):
            self._update_correlate_panel(self._samples[index].timestamp)

    def _on_chart_hover_left(self):
        for chart in self._charts:
            chart.set_crosshair(None)
        self._clear_correlate_panel()

    def _clear_correlate_panel(self):
        self._correlate_time_lbl.setVisible(False)
        self._correlate_empty.setText(_HINT_HOVER)
        self._correlate_empty.setVisible(True)
        self._correlate_chips.setVisible(False)
        self._clear_chips()

    def _clear_chips(self):
        """Seuls les chips sont vraiment recréés à chaque survol (nombre variable) — jamais
        _correlate_empty/_correlate_time_lbl, qui restent en permanence dans le layout."""
        while self._correlate_chips_layout.count():
            item = self._correlate_chips_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _update_correlate_panel(self, instant: datetime):
        self._clear_chips()

        self._correlate_time_lbl.setText(instant.strftime("%d/%m/%Y %H:%M"))
        self._correlate_time_lbl.setVisible(True)

        active = self._runs_active_at(instant)
        if not active:
            self._correlate_empty.setText(_HINT_NO_PIPELINE)
            self._correlate_empty.setVisible(True)
            self._correlate_chips.setVisible(False)
            return

        self._correlate_empty.setVisible(False)
        for r in active:
            name = r.pipeline.name if r.pipeline else str(r.pipeline_id)
            self._correlate_chips_layout.addWidget(self._pipeline_chip(name, r.started_at))
        # Sans ce ressort final, un seul chip (ou le dernier) s'étire pour occuper toute la
        # largeur du panneau au lieu de rester une pastille compacte alignée à gauche — repéré
        # sur une capture réelle. _clear_chips() vide tout à chaque cycle (widgets ET ressort),
        # donc il faut le rajouter à chaque repeuplement, pas une seule fois à la construction.
        self._correlate_chips_layout.addStretch()
        self._correlate_chips.setVisible(True)

    @staticmethod
    def _pipeline_chip(name: str, since: datetime) -> QWidget:
        chip = QFrame()
        chip.setStyleSheet(
            f"background: {COLORS['bg_hover']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 12px;"
        )
        layout = QHBoxLayout(chip)
        layout.setContentsMargins(10, 5, 12, 5)
        layout.setSpacing(7)
        dot = QLabel(); dot.setFixedSize(7, 7)
        dot.setStyleSheet(f"background: {_COLOR_COUNT}; border-radius: 3px;")
        layout.addWidget(dot)
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"color: {COLORS['text_main']}; font-size: 12px; font-weight: 500;")
        layout.addWidget(name_lbl)
        since_lbl = QLabel(f"depuis {since.strftime('%H:%M')}" if since else "")
        since_lbl.setStyleSheet(f"color: {COLORS['text_muted']}; font-family: {FONT_MONO}; font-size: 10.5px;")
        layout.addWidget(since_lbl)
        return chip
