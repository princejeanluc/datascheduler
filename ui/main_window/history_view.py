"""
DataScheduler — ui/main_window/history_view.py
Vue Historique : journal complet des exécutions.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QComboBox,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QColor
from ui.styles import COLORS
from .widgets import _icon, _action_btn, _configure_columns, _make_search_input, _make_empty_label, _make_title, _make_subtitle, _STATUS_BADGE, _status_str, FONT_MONO

_STATUS_FILTER_OPTIONS = [
    ("Tous les statuts", None),
    ("Succès", "SUCCESS"),
    ("Échec", "FAILED"),
    ("En cours", "RUNNING"),
    ("Annulé", "CANCELLED"),
]


class HistoryView(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)

        header = QHBoxLayout()
        title_col = QVBoxLayout(); title_col.setSpacing(2)
        title_col.addWidget(_make_title("Historique"))
        title_col.addWidget(_make_subtitle("Journal complet de toutes les exécutions"))
        header.addLayout(title_col); header.addStretch()
        btn_audit = QPushButton("  Journal des modifications"); btn_audit.setObjectName("secondary")
        btn_audit.setFixedHeight(36)
        btn_audit.setIcon(_icon("fa5s.history", COLORS["text_main"]))
        btn_audit.setIconSize(QSize(13, 13))
        btn_audit.clicked.connect(self._on_audit_log)
        header.addWidget(btn_audit)
        self.cb_status = QComboBox()
        self.cb_status.setFixedHeight(34)
        for label, value in _STATUS_FILTER_OPTIONS:
            self.cb_status.addItem(label, value)
        self.cb_status.currentIndexChanged.connect(self._apply_filters)
        header.addWidget(self.cb_status)
        self.inp_search = _make_search_input("Rechercher…")
        self.inp_search.textChanged.connect(self._apply_filters)
        header.addWidget(self.inp_search)
        layout.addLayout(header)

        sep = QFrame(); sep.setObjectName("separator"); sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        self._run_ids = []   # index ligne → run_id

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Pipeline", "Démarré le", "Durée", "Lignes", "Statut", "Fichier déposé", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        _configure_columns(self.table, stretch_cols={0, 5})
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 130)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed)
        self.table.setColumnWidth(6, 60)
        self.table.doubleClicked.connect(self._on_row_dbl_click)
        layout.addWidget(self.table)

        self._empty_label = _make_empty_label(
            "Aucune exécution enregistrée pour l'instant."
        )
        self._empty_label.setVisible(False)
        layout.addWidget(self._empty_label)
        layout.addStretch()

        self.refresh()

    def _apply_filters(self, *_args):
        """Combine le filtre de statut (colonne badge, égalité exacte) et la recherche libre
        (sous-chaîne insensible à la casse) — une ligne doit satisfaire les deux pour rester
        visible."""
        status = self.cb_status.currentData()
        needle = self.inp_search.text().strip().lower()
        search_cols = [0, 1, 2, 3, 4, 5]
        for row in range(self.table.rowCount()):
            badge = self.table.cellWidget(row, 4)
            if status is not None and (badge is None or badge.text() != status):
                self.table.setRowHidden(row, True)
                continue
            if not needle:
                self.table.setRowHidden(row, False)
                continue
            haystack = []
            for col in search_cols:
                item = self.table.item(row, col)
                if item:
                    haystack.append(item.text().lower())
                elif col == 4 and badge is not None:
                    haystack.append(badge.text().lower())
            self.table.setRowHidden(row, needle not in " ".join(haystack))

    def set_status_filter(self, status: str):
        idx = self.cb_status.findData(status)
        if idx >= 0:
            self.cb_status.setCurrentIndex(idx)
        else:
            self._apply_filters()

    def refresh(self):
        from database import db_manager as db
        runs = db.get_recent_runs(limit=100)
        self._run_ids = [r.id for r in runs]
        self.table.setVisible(bool(runs))
        self._empty_label.setVisible(not runs)
        self.table.setRowCount(len(runs))
        for r_idx, run in enumerate(runs):
            pname  = run.pipeline.name if run.pipeline else str(run.pipeline_id)
            st     = _status_str(run.status)
            dur    = "—"
            if run.duration_seconds is not None:
                m, s = divmod(int(run.duration_seconds), 60)
                dur  = f"{m}m {s:02d}s"
            date_s = run.started_at.strftime("%d/%m/%Y %H:%M:%S") if run.started_at else "—"
            rows_s = f"{run.rows_exported:,}".replace(",", " ") if run.rows_exported else "—"
            cells  = [pname, date_s, dur, rows_s, st, run.remote_path or "—"]
            for c_idx, cell in enumerate(cells):
                if c_idx == 4:
                    badge = QLabel(st); badge.setObjectName(_STATUS_BADGE.get(st, "badge_idle"))
                    badge.setAlignment(Qt.AlignCenter)
                    self.table.setCellWidget(r_idx, c_idx, badge)
                else:
                    item = QTableWidgetItem(cell)
                    item.setForeground(QColor(COLORS["text_dim"] if c_idx == 5 else COLORS["text_main"]))
                    if c_idx == 5:
                        item.setFont(QFont(FONT_MONO, 11))
                    self.table.setItem(r_idx, c_idx, item)

            btn_view = _action_btn("fa5s.search", object_name="secondary",
                                   tooltip="Voir le log complet", size=(26, 26))
            btn_view.clicked.connect(lambda _, i=r_idx: self._open_log(i))
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4)
            hl.addWidget(btn_view)
            self.table.setCellWidget(r_idx, 6, w)

            self.table.setRowHeight(r_idx, 44)

        self._apply_filters()

    def _on_row_dbl_click(self, index):
        self._open_log(index.row())

    def _open_log(self, row: int):
        if row >= len(self._run_ids):
            return
        from .run_log_dialog import open_run_log_dialog
        open_run_log_dialog(self, self._run_ids[row])

    @staticmethod
    def _build_audit_table(events) -> QTableWidget:
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["Date", "Type", "Pipeline", "Auteur", "Détail"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setShowGrid(False)
        _configure_columns(table, stretch_cols={4})

        table.setRowCount(len(events))
        for r_idx, event in enumerate(events):
            date_s = event.timestamp.strftime("%d/%m/%Y %H:%M:%S") if event.timestamp else "—"
            cells = [
                date_s, event.event_type, event.pipeline_name or "—",
                event.actor or "—", event.detail or "—",
            ]
            for c_idx, cell in enumerate(cells):
                item = QTableWidgetItem(cell)
                item.setForeground(QColor(COLORS["text_dim"] if c_idx == 4 else COLORS["text_main"]))
                table.setItem(r_idx, c_idx, item)
            table.setRowHeight(r_idx, 36)
        return table

    def _on_audit_log(self):
        from database import db_manager as db
        events = db.get_audit_events(limit=200)

        from PySide6.QtWidgets import QDialog, QVBoxLayout, QPushButton
        dlg = QDialog(self)
        dlg.setWindowTitle("Journal des modifications")
        dlg.setMinimumSize(760, 480)
        from ui.styles import DIALOG_STYLE
        dlg.setStyleSheet(DIALOG_STYLE)

        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 16, 20, 16)
        vl.setSpacing(12)

        lbl_title = QLabel("Journal des modifications")
        lbl_title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        vl.addWidget(lbl_title)

        table = self._build_audit_table(events)
        vl.addWidget(table)

        if not events:
            vl.addWidget(_make_empty_label("Aucun événement enregistré pour l'instant."))

        btn_close = QPushButton("Fermer")
        btn_close.setFixedHeight(34)
        btn_close.clicked.connect(dlg.accept)
        vl.addWidget(btn_close, alignment=Qt.AlignRight)

        dlg.exec()
