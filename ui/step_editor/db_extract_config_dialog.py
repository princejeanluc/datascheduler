"""
DataScheduler — ui/step_editor/db_extract_config_dialog.py
Dialogue de configuration d'une étape DB_EXTRACT.
"""

from PySide6.QtWidgets import (
    QVBoxLayout, QLabel, QSpinBox, QComboBox, QMessageBox,
)
from ui.styles import COLORS
from .base_config_dialog import _BaseStepConfigDialog
from .common import CSV_SEPARATORS, CSV_ENCODINGS, CSV_QUOTINGS


class _DbExtractConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "DB_EXTRACT"

    SEPARATORS = CSV_SEPARATORS
    ENCODINGS  = CSV_ENCODINGS
    QUOTINGS   = CSV_QUOTINGS

    def __init__(self, config: dict, parent=None, label: str = "",
                 oracle_profiles=None, sql_queries=None, ftp_profiles=None,
                 smtp_profiles=None, db_profiles=None,
                 retry_count: int = 0, run_always: bool = False,
                 prior_steps=None):
        super().__init__(config, parent, label, retry_count, run_always)
        self._db_profiles = db_profiles or []
        self._sql_queries  = sql_queries or []
        self.setWindowTitle("Étape — Extraction base de données")
        self.setMinimumSize(540, 500)
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Extraction base de données → CSV")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)
        self._add_execution_policy_row(form)
        self.cb_profile = self._db_profile_row(form, "Profil *", self._db_profiles)
        self.cb_query = self._profile_row(
            form, "Requête SQL *",
            self._sql_queries, "— Sélectionner une requête SQL —",
            self._new_sql_query,
        )
        self.cb_profile.currentIndexChanged.connect(self._filter_queries)

        # CSV
        self.cb_sep = QComboBox(); self.cb_sep.setStyleSheet(self._combo_style())
        for lbl, val in self.SEPARATORS: self.cb_sep.addItem(lbl, val)

        self.cb_enc = QComboBox(); self.cb_enc.setStyleSheet(self._combo_style())
        for lbl, val in self.ENCODINGS: self.cb_enc.addItem(lbl, val)

        self.inp_chunk = QSpinBox()
        self.inp_chunk.setRange(1_000, 1_000_000); self.inp_chunk.setValue(50_000)
        self.inp_chunk.setSingleStep(10_000); self.inp_chunk.setSuffix(" lignes")
        self.inp_chunk.setStyleSheet(self._spinbox_style())
        self.inp_chunk.setToolTip(
            "Nombre de lignes lues en mémoire à la fois — à réduire si le volume de données est "
            "très important."
        )

        self.cb_quoting = QComboBox(); self.cb_quoting.setStyleSheet(self._combo_style())
        for lbl, val in self.QUOTINGS: self.cb_quoting.addItem(lbl, val)
        self.cb_quoting.setToolTip(
            "Comment entourer les valeurs de guillemets dans le CSV produit — « Chaînes & dates "
            "seulement » convient à la plupart des imports Excel."
        )

        form.addRow(self._lbl("Séparateur CSV"),  self.cb_sep)
        form.addRow(self._lbl("Encodage"),        self.cb_enc)
        form.addRow(self._lbl("Taille chunk"),    self.inp_chunk)
        form.addRow(self._lbl("Guillemets CSV"),  self.cb_quoting)
        self.inp_output_name = self._output_name_row(form)
        root.addLayout(form)
        root.addStretch()
        self._buttons(root)

    def _prefill(self):
        c = self._config
        if c.get("db_type"):
            self._set_combo(self.cb_profile, (c.get("db_type"), c.get("profile_id")))
        self._filter_queries()
        self._set_combo(self.cb_query, c.get("sql_query_id"))
        self._set_combo_by_data(self.cb_sep,     c.get("csv_separator", ";"))
        self._set_combo_by_data(self.cb_enc,     c.get("csv_encoding",  "utf-8-sig"))
        self._set_combo_by_data(self.cb_quoting, c.get("csv_quoting",   "QUOTE_NONNUMERIC"))
        self.inp_chunk.setValue(c.get("csv_chunk_size", 50_000))
        self.inp_output_name.setText(c.get("output_name", ""))

    def _filter_queries(self):
        data = self.cb_profile.currentData()
        db_type, profile_id = data if data else (None, None)
        cur_qid = self.cb_query.currentData()
        self.cb_query.blockSignals(True)
        self.cb_query.clear()
        self.cb_query.addItem("— Sélectionner une requête SQL —", None)
        for q in self._sql_queries:
            # Le filtrage par profil n'a de sens que pour Oracle (SqlQuery.oracle_profile_id) ;
            # pour les autres moteurs, toutes les requêtes sont proposées sans filtre.
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
            "db_type":           db_type,
            "profile_id":        profile_id,
            "sql_query_id":      self.cb_query.currentData(),
            "csv_separator":     self.cb_sep.currentData(),
            "csv_encoding":      self.cb_enc.currentData(),
            "csv_chunk_size":    self.inp_chunk.value(),
            "csv_quoting":       self.cb_quoting.currentData(),
            "output_name":       self.inp_output_name.text().strip(),
        }

    def _on_ok(self):
        if not self.cb_profile.currentData():
            QMessageBox.warning(self, "Champ requis", "Sélectionner un profil de base de données.")
            return
        if not self.cb_query.currentData():
            QMessageBox.warning(self, "Champ requis", "Sélectionner une requête SQL.")
            return
        self.accept()

    @staticmethod
    def _set_combo_by_data(cb: QComboBox, value):
        for i in range(cb.count()):
            if cb.itemData(i) == value:
                cb.setCurrentIndex(i); return
