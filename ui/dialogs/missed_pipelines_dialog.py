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
from ui.styles import COLORS, DIALOG_STYLE, FONT_MONO_STACK


def _format_late(late_minutes: int) -> str:
    hours, minutes = divmod(late_minutes, 60)
    if hours:
        return f"{hours} h {minutes:02d}"
    return f"{minutes} min"


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
        row = QWidget()
        layout = QVBoxLayout(row)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(3)

        cb = QCheckBox(missed["name"])
        cb.setChecked(True)   # l'intention d'origine était de tourner sans surveillance
        cb.setStyleSheet(f"color: {COLORS['text_main']}; font-size: 13px; font-weight: 600;")
        cb.toggled.connect(self._refresh_selection_hint)
        self._checkboxes[missed["pipeline_id"]] = cb
        layout.addWidget(cb)

        when = QLabel(
            f"Prévu à {missed['expected_at'].strftime('%H:%M')} — manqué depuis "
            f"{_format_late(missed['late_minutes'])}"
        )
        when.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; font-family: {FONT_MONO_STACK}; "
            f"margin-left: 24px;"
        )
        layout.addWidget(when)
        return row

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
