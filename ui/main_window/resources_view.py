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

import math
from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame, QScrollArea,
)
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QFont

from ui.styles import COLORS, FONT_MONO, FONT_UI
from ui.time_display import fmt_datetime, fmt_time, to_display
from ui.components import make_page_header
from .widgets import StatCard

# Hues catégorielles validées (kit dataviz — CVD/contraste/luminosité, --pairs all en dark) —
# distinctes de COLORS['accent']/['signal'] (identité de marque/nav), jamais réutilisées pour
# une série de données (voir la maquette validée).
_COLOR_CPU   = "#3987e5"
_COLOR_RAM   = "#199e70"
_COLOR_COUNT = "#d95926"

_RANGES = [("1h", 1), ("6h", 6), ("24h", 24), ("7j", 24 * 7)]


def _interval_label(seconds: int) -> str:
    """« MINUTE » pour 60s (valeur par défaut, seule montrée sur la maquette), « N MINUTES »
    pour un multiple de 60 au-delà, « N SECONDES » sinon — couvre toute la plage réelle du
    réglage (QSpinBox 10-3600s, Paramètres > Ressources). Réutilisé par le surtitre (A1) et le
    texte de l'état vide (A9)."""
    if seconds % 60 == 0:
        minutes = seconds // 60
        return "MINUTE" if minutes == 1 else f"{minutes} MINUTES"
    return f"{seconds} SECONDES"

_HINT_HOVER = "Survolez un graphique pour voir le détail d'un instant."
_HINT_NO_PIPELINE = "Aucun pipeline en cours à cet instant."

# _MARGIN_LEFT élargi (4px à l'origine) pour loger les 2 graduations de valeur à gauche de
# chaque graphique (A2) — partagé par _TimeAxis (A3) pour que ses libellés de temps restent
# alignés en x avec les points des 3 graphiques.
_MARGIN_LEFT, _MARGIN_RIGHT, _MARGIN_TOP, _MARGIN_BOTTOM = 34, 4, 6, 6


def _format_peak_time(peak_local: datetime, today_local) -> str:
    """« aujourd'hui HH:MM » si le pic est tombé aujourd'hui (fuseau réglé), sinon
    « DD/MM HH:MM » — la maquette (Ressources.html) ne montre que des pics du jour même, cas non
    couvert ignoré plutôt que deviné (A7, note d'impact)."""
    if peak_local.date() == today_local:
        return f"aujourd'hui {peak_local.strftime('%H:%M')}"
    return peak_local.strftime("%d/%m %H:%M")


def _nice_ceiling(value: float) -> float:
    """Plus petite valeur « ronde » (1, 2 ou 5 × une puissance de 10) au-dessus de `value` — pour
    des graduations d'axe lisibles plutôt qu'un maximum brut (ex. « 200 »/« 100 » plutôt que
    « 182 »/« 91 »)."""
    if value <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(value))
    for mult in (1, 2, 5, 10):
        step = mult * magnitude
        if step >= value:
            return step
    return 10 * magnitude


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
        # Ligne de référence optionnelle (A6 — plafond d'exécutions simultanées sur le graphique
        # "Pipelines en cours" uniquement) : posée ici pour que _max_value() en tienne compte dès
        # ce commit, câblée (valeur + libellé réels, tracé) dans le commit A6.
        self._reference_value: float | None = None
        self._reference_label: str = ""
        self.setMinimumHeight(70)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)

    def set_data(self, values: list[float]) -> None:
        self._values = values
        self.update()

    def set_reference(self, value: float | None, label: str = "") -> None:
        self._reference_value = value
        self._reference_label = label
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
        raw = max(self._values, default=0)
        if self._reference_value is not None:
            raw = max(raw, self._reference_value)
        return _nice_ceiling(raw * 1.15) if raw > 0 else 1.0

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

        self._draw_grid(painter, plot)
        self._draw_reference(painter, plot)

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

    def _draw_grid(self, painter: QPainter, plot: QRectF) -> None:
        """Grille + 2 graduations de valeur à gauche (A2) : mi-hauteur et sommet de l'échelle —
        jamais « 0 » (ligne de base implicite, pas étiquetée sur la maquette)."""
        grid_pen = QPen(QColor(COLORS["bg_hover"])); grid_pen.setWidthF(1)
        label_pen = QPen(QColor(COLORS["text_muted"]))
        painter.setFont(QFont(FONT_MONO, 8))
        axis_max = self._max_value()
        for frac in (0.0, 0.5, 1.0):
            y = plot.bottom() - frac * plot.height()
            painter.setPen(grid_pen)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            if frac > 0.0:
                painter.setPen(label_pen)
                label_rect = QRectF(0, y - 7, _MARGIN_LEFT - 8, 14)
                painter.drawText(label_rect, Qt.AlignRight | Qt.AlignVCenter, f"{axis_max * frac:.0f}")

    def _draw_reference(self, painter: QPainter, plot: QRectF) -> None:
        """Ligne pointillée du plafond d'exécutions simultanées (A6, "Pipelines en cours"
        uniquement — set_reference() reste inerte/None pour CPU et RAM). Reprend exactement le
        style de la maquette (Ressources.html) : trait text_dim en tirets, libellé « plafond N »
        en Plex Sans (pas Mono, contrairement au reste du graphique) juste au-dessus."""
        if self._reference_value is None:
            return
        y = plot.bottom() - (self._reference_value / self._max_value()) * plot.height()
        dash_pen = QPen(QColor(COLORS["text_dim"]), 1)
        dash_pen.setDashPattern([4, 4])
        painter.setPen(dash_pen)
        painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        if self._reference_label:
            painter.setPen(QColor(COLORS["text_dim"]))
            painter.setFont(QFont(FONT_UI, 8))
            label_rect = QRectF(plot.right() - 120, y - 16, 120, 14)
            painter.drawText(label_rect, Qt.AlignRight | Qt.AlignVCenter, self._reference_label)

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


_DAY_ABBR = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]


class _TimeAxis(QWidget):
    """Axe du temps commun sous les 3 graphiques (A3) — mêmes marges gauche/droite que
    _TimeSeriesChart._plot_rect() pour un alignement x exact avec leurs points. Jamais une
    mesure indépendante : affiche seulement les timestamps déjà chargés par
    ResourcesView.refresh(), convertis au fuseau réglé (A4, ui.time_display). Se synchronise au
    même signal hovered/hover_left que les 3 graphiques (voir ResourcesView._on_chart_hover),
    sans en émettre lui-même — l'axe ne déclenche jamais le survol, il le suit."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timestamps: list[datetime] = []
        self._crosshair_index: int | None = None
        self.setFixedHeight(20)

    def set_data(self, timestamps: list[datetime]) -> None:
        self._timestamps = timestamps
        self.update()

    def set_crosshair(self, index: int | None) -> None:
        if index != self._crosshair_index:
            self._crosshair_index = index
            self.update()

    # ── Géométrie (même patron que _TimeSeriesChart) ──

    def _plot_rect(self) -> QRectF:
        return QRectF(
            _MARGIN_LEFT, 0,
            max(0.0, self.width() - _MARGIN_LEFT - _MARGIN_RIGHT),
            self.height(),
        )

    def _x_at(self, index: int) -> float:
        plot = self._plot_rect()
        n = len(self._timestamps)
        return plot.left() if n <= 1 else plot.left() + (index / (n - 1)) * plot.width()

    def _is_multiday(self) -> bool:
        if len(self._timestamps) < 2:
            return False
        return (self._timestamps[-1] - self._timestamps[0]) >= timedelta(hours=36)

    def _tick_indices(self) -> list[int]:
        """Un index par graduation voulue : un par jour calendaire (fuseau réglé) sur une plage
        multi-jours (7j), sinon un par pas d'heures « rond » choisi selon la durée totale
        couverte (3h en 24h, comme la fiche le prescrit ; 1h/6h ne sont précisées par aucune
        maquette — pas de valeur « ronde » à reprendre, choix de jugement signalé dans la note
        d'impact). Le premier échantillon n'est JAMAIS une graduation forcée : il tombe presque
        toujours au milieu d'un pas (la fenêtre glisse en continu, pas alignée sur une limite
        ronde), ce qui collait sinon un libellé juste à côté du suivant, à peine quelques
        minutes plus loin (chevauchement constaté à l'écran) — seul un changement de case entre
        deux échantillons CONSÉCUTIFS compte comme une graduation."""
        n = len(self._timestamps)
        if n < 2:
            return []
        local = [to_display(t) for t in self._timestamps]
        if self._is_multiday():
            bucket_of = lambda dt: dt.date()
        else:
            hours = (self._timestamps[-1] - self._timestamps[0]).total_seconds() / 3600
            step_minutes = 180 if hours > 8 else (60 if hours > 2 else 15)
            bucket_of = lambda dt: (dt.hour * 60 + dt.minute) // step_minutes

        indices = []
        previous_bucket = bucket_of(local[0])
        for i in range(1, n):
            bucket = bucket_of(local[i])
            if bucket != previous_bucket:
                indices.append(i)
                previous_bucket = bucket
        return indices

    def _label_for(self, dt: datetime) -> str:
        return f"{_DAY_ABBR[dt.weekday()]} {dt.day}" if self._is_multiday() else dt.strftime("%H:%M")

    # ── Rendu ──────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        plot = self._plot_rect()

        painter.setFont(QFont(FONT_MONO, 8))
        painter.setPen(QColor(COLORS["text_muted"]))
        for i in self._tick_indices():
            x = self._x_at(i)
            label = self._label_for(to_display(self._timestamps[i]))
            painter.drawText(QRectF(x - 30, 2, 60, 16), Qt.AlignCenter, label)

        if self._crosshair_index is not None and self._timestamps:
            idx = max(0, min(len(self._timestamps) - 1, self._crosshair_index))
            x = self._x_at(idx)
            text = to_display(self._timestamps[idx]).strftime("%H:%M")

            # Étiquette blanche de l'heure survolée (A3, Ressources-survol.html : <rect fill=
            # "#f2efeb"/><text fill="#141210">) — mêmes clés COLORS que le reste de l'appli,
            # jamais une couleur en dur, même si le résultat visuel est un encart clair isolé.
            painter.setFont(QFont(FONT_MONO, 9, QFont.DemiBold))
            width = painter.fontMetrics().horizontalAdvance(text) + 12
            rect = QRectF(min(max(x - width / 2, plot.left()), plot.right() - width), 1, width, 17)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(COLORS["text_main"]))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(QColor(COLORS["bg_main"]))
            painter.drawText(rect, Qt.AlignCenter, text)

        painter.end()


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
        from database import db_manager as db

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._range_buttons = {}
        range_buttons = []
        for label, hours in _RANGES:
            btn = QPushButton(label)
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda _, h=hours: self._on_range_changed(h))
            range_buttons.append(btn)
            self._range_buttons[hours] = btn

        interval_s = db.get_app_settings().resource_sample_interval_s
        header_widget = make_page_header(
            f"PROCESSUS KULU · UN POINT PAR {_interval_label(interval_s)}",
            "Ressources",
            "Utilisation de l'application dans le temps, pour repérer un lien avec vos "
            "pipelines. Ce n'est pas une mesure par pipeline : ils partagent le même processus.",
            actions=range_buttons,
        )
        header_widget.layout().setContentsMargins(32, 24, 32, 4)
        outer.addWidget(header_widget)

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

        self._time_axis = _TimeAxis()
        charts_layout.addWidget(self._time_axis)

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
        # Valeur + qualificatif séparés (A5) — "3 %  maintenant" au repos, "90 %  à l'instant
        # survolé" pendant un survol (Ressources-survol.html : 2 <span> de styles distincts).
        latest = QLabel("")
        latest.setStyleSheet(f"color: {COLORS['text_main']}; font-family: {FONT_MONO}; font-size: 12.5px; font-weight: 600;")
        layout.addWidget(latest)
        qualifier = QLabel("")
        qualifier.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
        layout.addWidget(qualifier)
        setattr(self, f"_lbl_{latest_attr}", latest)
        setattr(self, f"_lbl_{latest_attr}_qual", qualifier)
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
        self._time_axis.set_data([s.timestamp for s in self._samples])

        self._latest_chart_texts = (
            f"{cpu_values[-1]:.0f} %" if cpu_values else "—",
            f"{ram_values[-1]:.0f} Mo" if ram_values else "—",
            f"{count_values[-1]} en cours" if count_values else "—",
        )
        self._show_latest_chart_values()

        # Lecture seule d'un int (len() sur un dict) — pas besoin du verrou réel de
        # core.pipeline._active_runs_lock, juste utilisé ici pour affichage.
        running_now = len(pipeline_module._active_runs)
        max_concurrent = db.get_app_settings().max_concurrent_runs
        self._chart_count.set_reference(max_concurrent, f"plafond {max_concurrent}")
        self._card_running.set_value(f"{running_now} / {max_concurrent}")
        self._card_peak_cpu.set_value(f"{max(cpu_values, default=0):.0f} %")
        if cpu_values:
            peak_index = max(range(len(cpu_values)), key=lambda i: cpu_values[i])
            peak_local = to_display(self._samples[peak_index].timestamp)
            self._card_peak_cpu.set_subtitle(_format_peak_time(peak_local, to_display(datetime.utcnow()).date()))
        else:
            self._card_peak_cpu.set_subtitle("")
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

    # ── Titre de graphique : valeur survolée vs dernière valeur (A5) ──

    def _show_latest_chart_values(self):
        """État de repos des titres de graphique — dernière valeur connue, qualificatif
        « maintenant ». Mémorisé par refresh() (`_latest_chart_texts`) plutôt que recalculé ici,
        pour revenir à l'identique après un survol sans requêter la base à nouveau."""
        cpu_text, ram_text, count_text = self._latest_chart_texts
        self._lbl_latest_cpu.setText(cpu_text)
        self._lbl_latest_cpu_qual.setText("maintenant")
        self._lbl_latest_ram.setText(ram_text)
        self._lbl_latest_ram_qual.setText("maintenant")
        self._lbl_latest_count.setText(count_text)
        self._lbl_latest_count_qual.setText("maintenant")

    def _show_hovered_chart_values(self, sample) -> None:
        self._lbl_latest_cpu.setText(f"{sample.cpu_percent:.0f} %")
        self._lbl_latest_cpu_qual.setText("à l'instant survolé")
        self._lbl_latest_ram.setText(f"{sample.memory_mb:.0f} Mo")
        self._lbl_latest_ram_qual.setText("à l'instant survolé")
        self._lbl_latest_count.setText(f"{self._running_count_at(sample.timestamp)} en cours")
        self._lbl_latest_count_qual.setText("à l'instant survolé")

    # ── Curseur synchronisé + panneau de corrélation ──

    def _on_chart_hover(self, index: int):
        for chart in self._charts:
            chart.set_crosshair(index)
        self._time_axis.set_crosshair(index)
        if 0 <= index < len(self._samples):
            sample = self._samples[index]
            self._show_hovered_chart_values(sample)
            self._update_correlate_panel(sample)

    def _on_chart_hover_left(self):
        for chart in self._charts:
            chart.set_crosshair(None)
        self._time_axis.set_crosshair(None)
        self._show_latest_chart_values()
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

    def _update_correlate_panel(self, sample) -> None:
        self._clear_chips()

        instant = sample.timestamp
        active = self._runs_active_at(instant)
        # Ligne de résumé (A8, Ressources-survol.html) : date/heure déjà affichées, étendues ici
        # avec le nombre de pipelines actifs, le CPU et la mémoire de l'échantillon survolé —
        # toujours affichée pendant un survol, même sans pipeline actif (la fiche ne conditionne
        # pas A8 à "active"). Porte un badge "proposé" sur la maquette, mais listée en Lot A (A8).
        pipeline_word = "pipeline actif" if len(active) <= 1 else "pipelines actifs"
        self._correlate_time_lbl.setText(
            f"{fmt_datetime(instant)} · {len(active)} {pipeline_word} · "
            f"CPU {sample.cpu_percent:.0f} % · mémoire {sample.memory_mb:.0f} Mo"
        )
        self._correlate_time_lbl.setVisible(True)

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
        since_lbl = QLabel(f"depuis {fmt_time(since, fmt='%H:%M')}" if since else "")
        since_lbl.setStyleSheet(f"color: {COLORS['text_muted']}; font-family: {FONT_MONO}; font-size: 10.5px;")
        layout.addWidget(since_lbl)
        return chip
