"""
DataScheduler — ui/dialogs/missed_pipelines_dialog.py
Dialogue affiché une fois au démarrage (chantier rattrapage des pipelines manqués) : liste les
pipelines détectés par core.missed_runs.detect_missed_runs() et propose de les lancer
maintenant. Décocher un pipeline (ou "Plus tard") ne l'efface jamais — il reste dans
core.missed_runs jusqu'à lancement ou "Ignorer" explicite, retrouvable ensuite dans le bandeau
du Dashboard.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QWidget,
    QCheckBox, QScrollArea,
)
from ui.styles import COLORS, DIALOG_STYLE
from ui.time_display import fmt_time_local

# Jours en français écrits en dur (A11), même patron que dashboard_view.py::_DAYS_FR — pas de
# dépendance à la locale système dans un exécutable packagé.
_DAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _format_late(late_minutes: int) -> str:
    """Étendu aux jours (A11, « 1 j 2 h ») — au-delà de 24h, les minutes ne sont plus montrées
    (précision inutile à cette échelle, maquette Aujourdhui-rattrapage.html)."""
    days, remainder = divmod(late_minutes, 24 * 60)
    hours, minutes = divmod(remainder, 60)
    if days:
        return f"{days} j {hours} h" if hours else f"{days} j"
    if hours:
        return f"{hours} h {minutes:02d}"
    return f"{minutes} min"


def _format_expected_at(expected_at) -> str:
    """« prévue samedi 07:00 » (A11) — jour de la semaine complet, pas seulement l'heure."""
    return f"{_DAYS_FR[expected_at.weekday()]} {fmt_time_local(expected_at)}"


class MissedPipelinesDialog(QDialog):
    """`missed` : la forme retournée par core.missed_runs.detect_missed_runs()/get_pending() —
    liste de {"pipeline_id", "name", "expected_at", "late_minutes"}."""

    def __init__(self, parent=None, missed: list[dict] | None = None):
        super().__init__(parent)
        self._missed = missed or []
        self._checkboxes: dict[int, QCheckBox] = {}
        plural = "s" if len(self._missed) > 1 else ""
        self.setWindowTitle(f"{len(self._missed)} pipeline{plural} manqué{plural}")
        self.setMinimumWidth(460)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QWidget()
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(22, 20, 22, 16)
        head_layout.setSpacing(12)

        icon_badge = QLabel("!")
        icon_badge.setFixedSize(34, 34)
        icon_badge.setAlignment(Qt.AlignCenter)
        icon_badge.setStyleSheet(
            f"background: {COLORS['warning']}22; color: {COLORS['warning']}; "
            f"border-radius: 9px; font-size: 16px; font-weight: 700;"
        )
        head_layout.addWidget(icon_badge)

        plural = "s" if len(self._missed) > 1 else ""
        title_col = QVBoxLayout(); title_col.setSpacing(3)
        title = QLabel(f"{len(self._missed)} pipeline{plural} manqué{plural} son{plural} exécution")
        title.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {COLORS['text_main']};")
        title.setWordWrap(True)
        subtitle = QLabel(
            "Manqués pendant que l'application était fermée. Décocher n'efface rien — "
            "retrouvable ensuite dans le bandeau du Dashboard."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        title_col.addWidget(title); title_col.addWidget(subtitle)
        head_layout.addLayout(title_col, stretch=1)
        root.addWidget(head)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        root.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMaximumHeight(280)
        inner = QWidget()
        rows = QVBoxLayout(inner)
        rows.setContentsMargins(22, 12, 22, 12)
        rows.setSpacing(2)

        for m in self._missed:
            rows.addWidget(self._make_row(m))
        scroll.setWidget(inner)
        root.addWidget(scroll)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        root.addWidget(sep2)

        foot = QHBoxLayout()
        foot.setContentsMargins(22, 14, 22, 18)
        foot.setSpacing(10)
        self.lbl_selected = QLabel("")
        self.lbl_selected.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        foot.addWidget(self.lbl_selected)
        foot.addStretch()
        btn_later = QPushButton("Plus tard"); btn_later.setObjectName("secondary")
        btn_later.setFixedHeight(34); btn_later.clicked.connect(self.reject)
        self.btn_launch = QPushButton("Lancer la sélection")
        self.btn_launch.setFixedHeight(34)
        self.btn_launch.clicked.connect(self._on_launch_selected)
        foot.addWidget(btn_later); foot.addWidget(self.btn_launch)
        root.addLayout(foot)

        self._refresh_selection_hint()

    def _make_row(self, missed: dict) -> QWidget:
        # Carte (A11, Aujourdhui-rattrapage.html) — chaque ligne était du texte nu empilé avant
        # ce lot, la maquette la montre en encart teinté (mêmes clés COLORS que les bandeaux
        # d'avertissement ailleurs dans l'appli, pas les valeurs exactes de la maquette qui ne
        # correspondent à aucune clé existante — REGLES.md section 3).
        card = QFrame()
        # Sélecteur d'ID, pas une règle nue : QLabel hérite de QFrame en Qt, une règle nue sur
        # le type QFrame se propage à chaque QLabel enfant sans bordure propre — la ligne
        # "prévue..." se retrouvait encadrée séparément du reste de la carte (bug constaté à
        # l'écran, reproduit isolément). Même précaution que partout ailleurs dans la refonte
        # (REGLES.md section 3).
        card.setObjectName("missed_row")
        card.setStyleSheet(
            f"QFrame#missed_row {{ background: {COLORS['bg_warning']}; "
            f"border: 1px solid {COLORS['border_warning']}; border-radius: 8px; }}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)

        cb = QCheckBox(missed["name"])
        cb.setChecked(True)   # l'intention d'origine était de tourner sans surveillance
        cb.setStyleSheet(f"color: {COLORS['text_main']}; font-size: 13px; font-weight: 600;")
        cb.toggled.connect(self._refresh_selection_hint)
        self._checkboxes[missed["pipeline_id"]] = cb
        layout.addWidget(cb)

        when = QLabel(
            f"prévue {_format_expected_at(missed['expected_at'])} · en retard de "
            f"{_format_late(missed['late_minutes'])}"
        )
        when.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 12px; margin-left: 24px;"
        )
        layout.addWidget(when)
        return card

    def _refresh_selection_hint(self):
        total = len(self._missed)
        checked = sum(1 for cb in self._checkboxes.values() if cb.isChecked())
        self.lbl_selected.setText(f"{checked} sur {total} sélectionné{'s' if total > 1 else ''}")
        self.btn_launch.setEnabled(checked > 0)

    def _on_launch_selected(self):
        from core.missed_runs import resolve
        try:
            from core.scheduler import get_scheduler
            scheduler = get_scheduler()
        except RuntimeError:
            scheduler = None

        for pipeline_id, cb in self._checkboxes.items():
            if not cb.isChecked():
                continue   # laissé en attente — réapparaîtra dans le bandeau du Dashboard
            if scheduler is not None:
                scheduler.trigger_now(pipeline_id)
            resolve(pipeline_id)

        self.accept()
