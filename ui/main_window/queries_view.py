"""
DataScheduler — ui/main_window/queries_view.py
Vue Requêtes SQL : bibliothèque de requêtes réutilisables.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QFrame, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QMessageBox,
)
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor
from ui.styles import COLORS
from .widgets import _icon, _action_btn, _configure_columns, _filter_table_rows, _make_search_input, _make_empty_label, _make_title, _make_subtitle


class QueriesView(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)

        header = QHBoxLayout()
        col = QVBoxLayout(); col.setSpacing(2)
        col.addWidget(_make_title("Requêtes SQL"))
        col.addWidget(_make_subtitle("Bibliothèque de requêtes réutilisables"))
        header.addLayout(col); header.addStretch()
        self.inp_search = _make_search_input("Rechercher une requête…")
        self.inp_search.textChanged.connect(self._on_search_changed)
        header.addWidget(self.inp_search)
        btn = QPushButton("  Nouvelle requête"); btn.setFixedHeight(36)
        btn.setIcon(_icon("fa5s.plus", "#000000")); btn.setIconSize(QSize(13, 13))
        btn.clicked.connect(self._on_new_query)
        header.addWidget(btn)
        layout.addLayout(header)

        sep = QFrame(); sep.setObjectName("separator"); sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Nom", "Description", "Utilisée par", "Actions"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        _configure_columns(self.table, stretch_cols={0, 1})
        self.table.setColumnWidth(3, 100)
        layout.addWidget(self.table)

        self._empty_label = _make_empty_label(
            "Aucune requête enregistrée — cliquez sur « Nouvelle requête » pour créer la première."
        )
        self._empty_label.setVisible(False)
        layout.addWidget(self._empty_label)
        layout.addStretch()

        self.refresh()

    def _on_search_changed(self, text: str):
        _filter_table_rows(self.table, text, columns=[0, 1, 2])

    def refresh(self):
        from database import db_manager as db
        queries = db.get_sql_queries()
        self.table.setVisible(bool(queries))
        self._empty_label.setVisible(not queries)
        self.table.setRowCount(len(queries))
        for r_idx, q in enumerate(queries):
            used_by = db.find_pipelines_using_profile("sql_query_id", q.id)
            usage = f"{len(used_by)} pipeline(s)" if used_by else "Aucun"
            cells = [q.name, q.description or "—", usage]
            for c_idx, cell in enumerate(cells):
                item = QTableWidgetItem(cell)
                item.setForeground(QColor(COLORS["text_main"]))
                if c_idx == 0:
                    item.setToolTip(q.sql_text)
                elif c_idx == 2 and used_by:
                    item.setToolTip(", ".join(used_by))
                self.table.setItem(r_idx, c_idx, item)
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4); hl.setSpacing(6)
            btn_edit = _action_btn("fa5s.pencil-alt", object_name="secondary", tooltip="Modifier",   size=(30, 28))
            btn_del  = _action_btn("fa5s.trash-alt",  object_name="danger",    tooltip="Supprimer",  size=(30, 28))
            qid = q.id
            btn_edit.clicked.connect(lambda _, i=qid: self._on_edit_query(i))
            btn_del.clicked.connect(lambda _, i=qid: self._on_delete_query(i))
            hl.addWidget(btn_edit); hl.addWidget(btn_del); hl.addStretch()
            self.table.setCellWidget(r_idx, 3, w)
            self.table.setRowHeight(r_idx, 48)

        self._on_search_changed(self.inp_search.text())

    def _on_new_query(self):
        from ui.dialogs import SqlQueryDialog
        if SqlQueryDialog(self).exec():
            self.refresh()

    def _on_edit_query(self, query_id: int):
        from database import db_manager as db
        from ui.dialogs import SqlQueryDialog
        q = db.get_sql_query(query_id)
        if q and SqlQueryDialog(self, query=q).exec():
            self.refresh()

    def _on_delete_query(self, query_id: int):
        from database import db_manager as db
        used_by = db.find_pipelines_using_profile("sql_query_id", query_id)
        if used_by:
            names = ", ".join(used_by)
            msg = (
                f"Cette requête est utilisée par {len(used_by)} pipeline(s) : {names}.\n\n"
                f"La supprimer quand même ? Ces pipelines échoueront à leur prochaine exécution."
            )
        else:
            msg = "Supprimer cette requête ?"
        reply = QMessageBox.question(self, "Supprimer", msg, QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            db.delete_sql_query(query_id)
            self.refresh()
