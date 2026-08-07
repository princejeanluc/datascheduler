"""
DataScheduler — ui/step_editor/db_load_config_dialog.py
Dialogue de configuration d'une étape DB_LOAD.
"""

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QSpinBox, QCheckBox,
    QFileDialog, QMessageBox,
)
from ui.styles import COLORS
from .base_config_dialog import _BaseStepConfigDialog


class _DbLoadConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "DB_LOAD"

    def __init__(self, config: dict, parent=None, label: str = "",
                 oracle_profiles=None, sql_queries=None, ftp_profiles=None,
                 smtp_profiles=None, db_profiles=None,
                 retry_count: int = 0, run_always: bool = False, timeout_s: int = 0,
                 prior_steps=None):
        super().__init__(config, parent, label, retry_count, run_always, timeout_s)
        self._db_profiles = db_profiles or []
        self._prior_steps = prior_steps or []
        self.setWindowTitle("Étape — Chargement base de données")
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Chargement CSV → table")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)
        self._add_execution_policy_row(form)
        self.cb_profile = self._db_profile_row(form, "Profil *", self._db_profiles)
        self.cb_source = self._source_row(form, self._prior_steps)

        self.inp_explicit_path = self._input("ex : C:/data/export_{yyyyMMdd}.csv")
        path_row = QHBoxLayout(); path_row.setSpacing(6)
        path_row.addWidget(self.inp_explicit_path, stretch=1)
        btn_browse = QPushButton("Parcourir…"); btn_browse.setObjectName("secondary")
        btn_browse.setFixedHeight(34); btn_browse.setFixedWidth(100)
        btn_browse.clicked.connect(self._browse_source_file)
        path_row.addWidget(btn_browse)
        path_widget = QWidget(); path_widget.setLayout(path_row)
        form.addRow(self._lbl("Chemin source explicite"), path_widget)
        hint = QLabel(
            "Si renseigné, prioritaire sur la Source ci-dessus — utile quand cette étape est la "
            "seule du pipeline."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; font-style: italic;")
        form.addRow("", hint)

        self.inp_table = self._input("ex : VENTES_STAGING")
        form.addRow(self._lbl("Table cible *"), self.inp_table)

        note = QLabel("Les colonnes du CSV doivent correspondre aux noms de colonnes de la table.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; font-style: italic;")
        form.addRow("", note)

        self.chk_truncate = QCheckBox("Vider la table avant chargement (TRUNCATE)")
        self.chk_truncate.setStyleSheet(f"color: {COLORS['text_main']};")
        self.chk_truncate.setToolTip(
            "Supprime toutes les lignes existantes de la table avant le chargement — "
            "irréversible, à utiliser avec prudence sur une table déjà en production."
        )
        form.addRow("", self.chk_truncate)

        self.inp_chunk = QSpinBox()
        self.inp_chunk.setRange(1_000, 1_000_000); self.inp_chunk.setValue(50_000)
        self.inp_chunk.setSingleStep(10_000); self.inp_chunk.setSuffix(" lignes")
        self.inp_chunk.setStyleSheet(self._spinbox_style())
        self.inp_chunk.setToolTip(
            "Nombre de lignes insérées par lot — à réduire en cas de table volumineuse ou de "
            "mémoire limitée."
        )
        form.addRow(self._lbl("Taille chunk"), self.inp_chunk)
        root.addLayout(form)
        root.addStretch()
        self._buttons(root)

    def _browse_source_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choisir le fichier source")
        if path:
            self.inp_explicit_path.setText(path)

    def _prefill(self):
        c = self._config
        if c.get("db_type"):
            self._set_combo(self.cb_profile, (c.get("db_type"), c.get("profile_id")))
        self._set_combo(self.cb_source, c.get("reads_from_step_key"))
        self.inp_explicit_path.setText(c.get("explicit_path", ""))
        self.inp_table.setText(c.get("table_name", ""))
        self.chk_truncate.setChecked(c.get("truncate_before_load", False))
        self.inp_chunk.setValue(c.get("csv_chunk_size", 50_000))

    def _collect_config(self) -> dict:
        data = self.cb_profile.currentData()
        db_type, profile_id = data if data else (None, None)
        return {
            "db_type":              db_type,
            "profile_id":           profile_id,
            "table_name":           self.inp_table.text().strip(),
            "truncate_before_load": self.chk_truncate.isChecked(),
            "csv_chunk_size":       self.inp_chunk.value(),
            "reads_from_step_key":  self.cb_source.currentData(),
            "explicit_path":        self.inp_explicit_path.text().strip(),
        }

    def _on_ok(self):
        if not self.cb_profile.currentData():
            QMessageBox.warning(self, "Champ requis", "Sélectionner un profil de base de données.")
            return
        if not self.inp_table.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir la table cible.")
            return
        self.accept()
