"""
DataScheduler — ui/dialogs/pipeline_detail_dialog.py
Vue détaillée d'un pipeline (chantier UX fiabilité, D.1) : activité récente (graphique + résumé)
et table des dernières exécutions — ouverte au double-clic sur une ligne de PipelinesView, même
mécanique que HistoryView pour ses lignes de run.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QWidget,
    QTableWidget, QTableWidgetItem, QAbstractItemView,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from ui.styles import COLORS, DIALOG_STYLE
from ui.main_window.widgets import _action_btn, _configure_columns, _status_str, FONT_MONO
from ui.main_window.activity_chart import ActivityChartWidget
from ui.main_window.run_log_dialog import open_run_log_dialog

_STATUS_COLOR = {
    "SUCCESS": "success",
    "FAILED":  "danger",
    "RUNNING": "accent",
}


class PipelineDetailDialog(QDialog):
    def __init__(self, parent, pipeline):
        super().__init__(parent)
        self._pipeline = pipeline
        self._run_ids: list[int] = []
        self.setWindowTitle(f"Détail — {pipeline.name}")
        self.setMinimumSize(720, 620)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        title_col = QVBoxLayout(); title_col.setSpacing(2)
        lbl_name = QLabel(self._pipeline.name)
        lbl_name.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {COLORS['text_main']};")
        title_col.addWidget(lbl_name)
        if self._pipeline.description:
            lbl_desc = QLabel(self._pipeline.description)
            lbl_desc.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
            lbl_desc.setWordWrap(True)
            title_col.addWidget(lbl_desc)
        header.addLayout(title_col); header.addStretch()

        st = "INACTIF" if not self._pipeline.is_active else _status_str(self._pipeline.last_status)
        color_key = "text_dim" if not self._pipeline.is_active else _STATUS_COLOR.get(st, "text_dim")
        badge = QLabel(st)
        badge.setStyleSheet(
            f"color: {COLORS[color_key]}; background: transparent; border: 1px solid {COLORS[color_key]}; "
            f"border-radius: 3px; padding: 3px 10px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px;"
        )
        header.addWidget(badge)
        root.addLayout(header)

        root.addWidget(self._sep())

        self.lbl_summary = QLabel("—")
        self.lbl_summary.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
        root.addWidget(self.lbl_summary)

        if self._pipeline.trigger_after_pipeline_id:
            parent_name = (self._pipeline.trigger_after_pipeline.name
                            if self._pipeline.trigger_after_pipeline else "?")
            cond_label = {"SUCCESS": "Succès", "FAILURE": "Échec", "ALWAYS": "Toujours"}.get(
                _status_str(self._pipeline.trigger_condition), "—"
            )
            lbl_trigger = QLabel(f"Déclenché après : « {parent_name} » ({cond_label})")
            lbl_trigger.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
            root.addWidget(lbl_trigger)

        lbl_activity = QLabel("Activité (30 derniers jours)")
        lbl_activity.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {COLORS['text_main']};")
        root.addWidget(lbl_activity)

        self.chart = ActivityChartWidget()
        self.chart.setFixedHeight(120)
        root.addWidget(self.chart)

        lbl_runs = QLabel("Dernières exécutions")
        lbl_runs.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {COLORS['text_main']};")
        root.addWidget(lbl_runs)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Démarré le", "Durée", "Lignes", "Statut", "Fichier déposé", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        _configure_columns(self.table, stretch_cols={0, 4})
        self.table.doubleClicked.connect(lambda idx: self._open_log(idx.row()))
        root.addWidget(self.table, stretch=1)

        btn_row = QHBoxLayout(); btn_row.addStretch()
        btn_close = QPushButton("Fermer")
        btn_close.setFixedHeight(34)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f

    def _load_data(self):
        from database import db_manager as db

        counts = db.get_run_counts_by_day(days=30, pipeline_id=self._pipeline.id)
        self.chart.set_data(counts)

        total = sum(d["success"] + d["failed"] + d["cancelled"] for d in counts)
        success = sum(d["success"] for d in counts)
        rate = f"{success / total * 100:.0f} %" if total else "—"
        self.lbl_summary.setText(f"{total} exécution(s) sur 30 jours — {rate} de succès")

        runs = db.get_runs(self._pipeline.id, limit=50)
        self._run_ids = [r.id for r in runs]
        self.table.setRowCount(len(runs))
        for r_idx, run in enumerate(runs):
            st = _status_str(run.status)
            dur = "—"
            if run.duration_seconds is not None:
                m, s = divmod(int(run.duration_seconds), 60)
                dur = f"{m}m {s:02d}s"
            date_s = run.started_at.strftime("%d/%m/%Y %H:%M") if run.started_at else "—"
            rows_s = f"{run.rows_exported:,}".replace(",", " ") if run.rows_exported else "—"
            cells = [date_s, dur, rows_s, st, run.remote_path or "—"]
            for c_idx, cell in enumerate(cells):
                if c_idx == 3:
                    color_key = "text_dim" if st not in _STATUS_COLOR else _STATUS_COLOR[st]
                    badge = QLabel(st)
                    badge.setAlignment(Qt.AlignCenter)
                    badge.setStyleSheet(
                        f"color: {COLORS[color_key]}; background: transparent; font-size: 11px; "
                        f"font-weight: 700;"
                    )
                    self.table.setCellWidget(r_idx, c_idx, badge)
                else:
                    item = QTableWidgetItem(cell)
                    item.setForeground(QColor(COLORS["text_dim"] if c_idx == 4 else COLORS["text_main"]))
                    if c_idx == 4:
                        item.setFont(QFont(FONT_MONO, 11))
                    self.table.setItem(r_idx, c_idx, item)

            btn_view = _action_btn("fa5s.search", object_name="secondary",
                                    tooltip="Voir le log complet", size=(26, 26))
            btn_view.clicked.connect(lambda _, i=r_idx: self._open_log(i))
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4)
            hl.addWidget(btn_view)
            self.table.setCellWidget(r_idx, 5, w)
            self.table.setRowHeight(r_idx, 40)

    def _open_log(self, row: int):
        if row >= len(self._run_ids):
            return
        open_run_log_dialog(self, self._run_ids[row])
