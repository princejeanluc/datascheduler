"""
DataScheduler — ui/step_editor/db_execute_config_dialog.py
Dialogue de configuration d'une étape DB_EXECUTE.
"""

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QFrame,
    QCheckBox, QMessageBox,
)
from PySide6.QtCore import QThread, Signal
from ui.styles import COLORS
from .base_config_dialog import _BaseStepConfigDialog


class _DbExecuteTestThread(QThread):
    """Exécute le SQL réel puis annule (rollback) — ne persiste rien."""
    result_ready = Signal(bool, str, int)   # success, message, rows_affected

    def __init__(self, db_type: str, profile, sql_text: str):
        super().__init__()
        self.db_type = db_type
        self.profile = profile
        self.sql_text = sql_text

    def run(self):
        try:
            from sqlalchemy import text
            from core.sql_db import SqlConnector, config_from_profile, is_plsql_block
            cfg = config_from_profile(self.db_type, self.profile)
            connector = SqlConnector(cfg)
            connector.connect()
            plsql = False
            try:
                plsql = self.db_type == "ORACLE" and is_plsql_block(self.sql_text)
                cursor_result = connector.connection.execute(text(self.sql_text))
                rows = -1 if plsql else cursor_result.rowcount
                connector.connection.rollback()
            finally:
                connector.disconnect()
            msg = "Exécution réussie — annulée, rien n'a été persisté."
            if plsql:
                msg += (" Bloc PL/SQL : le nombre de lignes affectées par une instruction "
                        "DML interne (ex. via une procédure stockée) n'est pas mesurable ici.")
            self.result_ready.emit(True, msg, rows)
        except Exception as e:
            self.result_ready.emit(False, str(e), 0)


class _DbExecuteConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "DB_EXECUTE"

    def __init__(self, config: dict, parent=None, label: str = "",
                 oracle_profiles=None, sql_queries=None, ftp_profiles=None,
                 smtp_profiles=None, db_profiles=None,
                 retry_count: int = 0, run_always: bool = False, timeout_s: int = 0,
                 retry_interval_s: int = 5, prior_steps=None):
        super().__init__(config, parent, label, retry_count, run_always, timeout_s,
                          retry_interval_s)
        self._db_profiles = db_profiles or []
        self._sql_queries  = sql_queries or []
        self._test_thread  = None
        self.setWindowTitle("Étape — Exécution base de données")
        self.setMinimumSize(540, 460)
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Exécution SQL / PLSQL (DML, DDL, procédure)")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)
        self._add_execution_policy_row(form)
        self.cb_profile = self._db_profile_row(form, "Profil *", self._db_profiles)
        self.cb_query = self._profile_row(
            form, "Requête / instruction *",
            self._sql_queries, "— Sélectionner une requête SQL —",
            self._new_sql_query,
        )
        self.cb_profile.currentIndexChanged.connect(self._filter_queries)

        self.chk_commit = QCheckBox("Valider (commit) automatiquement après exécution")
        self.chk_commit.setChecked(True)
        self.chk_commit.setStyleSheet(f"color: {COLORS['text_main']};")
        self.chk_commit.setToolTip(
            "Décochez uniquement si vous gérez déjà la validation vous-même dans la requête ou "
            "la procédure stockée."
        )
        form.addRow("", self.chk_commit)
        root.addLayout(form)

        note = QLabel(
            "Une étape = une instruction ou un bloc PL/SQL complet (pas de découpage sur ';'). "
            "Pour un script à plusieurs étapes, chaîner plusieurs étapes DB_EXECUTE."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; font-style: italic;")
        root.addWidget(note)

        root.addWidget(self._build_test_zone())
        root.addStretch()
        self._buttons(root)

    def _build_test_zone(self) -> QFrame:
        frame = QFrame(); frame.setObjectName("card")
        hl = QHBoxLayout(frame); hl.setContentsMargins(14, 10, 14, 10); hl.setSpacing(12)
        self.btn_test = QPushButton("⚡  Tester (exécute + annule)")
        self.btn_test.setObjectName("secondary"); self.btn_test.setFixedHeight(32)
        self.btn_test.clicked.connect(self._on_test)
        self.lbl_test_result = QLabel("—")
        self.lbl_test_result.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
        hl.addWidget(self.btn_test); hl.addWidget(self.lbl_test_result, stretch=1)
        return frame

    def _on_test(self):
        from core.sql_db import get_profile_object
        data  = self.cb_profile.currentData()
        query = next((q for q in self._sql_queries if q.id == self.cb_query.currentData()), None)
        if not data or not query:
            QMessageBox.warning(self, "Champ requis", "Sélectionner un profil et une requête.")
            return
        db_type, profile_id = data
        profile = get_profile_object(db_type, profile_id)
        if not profile:
            QMessageBox.warning(self, "Erreur", "Profil introuvable.")
            return
        from core.steps.base import StepContext
        sql_text = StepContext().resolve_tokens(query.sql_text)

        self.btn_test.setEnabled(False)
        self.lbl_test_result.setText("Exécution en cours…")
        self.lbl_test_result.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
        self._test_thread = _DbExecuteTestThread(db_type, profile, sql_text)
        self._test_thread.result_ready.connect(self._on_test_result)
        self._test_thread.start()

    def _on_test_result(self, success: bool, message: str, rows: int):
        self.btn_test.setEnabled(True)
        if success:
            txt   = f"✅  {message}" if rows < 0 else f"✅  {message} ({rows} ligne(s) affectée(s))"
            color = COLORS["success"]
        else:
            txt   = f"❌  {message}"
            color = COLORS["danger"]
        self.lbl_test_result.setText(txt)
        self.lbl_test_result.setStyleSheet(f"color: {color}; font-size: 12px;")

    def _prefill(self):
        c = self._config
        if c.get("db_type"):
            self._set_combo(self.cb_profile, (c.get("db_type"), c.get("profile_id")))
        self._filter_queries()
        self._set_combo(self.cb_query, c.get("sql_query_id"))
        self.chk_commit.setChecked(c.get("commit", True))

    def _filter_queries(self):
        data = self.cb_profile.currentData()
        db_type, profile_id = data if data else (None, None)
        cur_qid = self.cb_query.currentData()
        self.cb_query.blockSignals(True)
        self.cb_query.clear()
        self.cb_query.addItem("— Sélectionner une requête SQL —", None)
        for q in self._sql_queries:
            if (db_type != "ORACLE" or profile_id is None
                    or q.oracle_profile_id == profile_id or q.oracle_profile_id is None):
                self.cb_query.addItem(q.name, q.id)
        self._set_combo(self.cb_query, cur_qid)
        self.cb_query.blockSignals(False)

    def _new_sql_query(self, cb: QComboBox):
        from ui.dialogs import SqlQueryDialog
        from database import db_manager as db
        if SqlQueryDialog(self).exec():
            self._sql_queries = db.get_sql_queries()
            self._filter_queries()
            self._set_combo(cb, self._sql_queries[-1].id if self._sql_queries else None)

    def _collect_config(self) -> dict:
        data = self.cb_profile.currentData()
        db_type, profile_id = data if data else (None, None)
        return {
            "db_type":      db_type,
            "profile_id":   profile_id,
            "sql_query_id": self.cb_query.currentData(),
            "commit":       self.chk_commit.isChecked(),
        }

    def _on_ok(self):
        if not self.cb_profile.currentData():
            QMessageBox.warning(self, "Champ requis", "Sélectionner un profil de base de données.")
            return
        if not self.cb_query.currentData():
            QMessageBox.warning(self, "Champ requis", "Sélectionner une requête/instruction.")
            return
        self.accept()
