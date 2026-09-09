"""
DataScheduler — ui/step_editor/sqoop_import_config_dialog.py
Dialogue de configuration d'une étape SQOOP_IMPORT.
"""

from PySide6.QtWidgets import (
    QVBoxLayout, QLabel, QComboBox, QPlainTextEdit, QSpinBox, QMessageBox, QWidget, QScrollArea,
    QFrame,
)
from PySide6.QtGui import QFont
from ui.styles import COLORS, FONT_MONO
from .base_config_dialog import _BaseStepConfigDialog


class _SqoopImportConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "SQOOP_IMPORT"

    def __init__(self, config: dict, parent=None, label: str = "", **_):
        super().__init__(config, parent, label,
                          retry_count=_.get("retry_count", 0),
                          retry_interval_s=_.get("retry_interval_s", 5),
                          run_always=_.get("run_always", False),
                          timeout_s=_.get("timeout_s", 0))
        from database import db_manager as db
        # ssh_profiles/kerberos_profiles/elevation_profiles ne font pas partie du kwargs partagé
        # de _open_config_dialog() (oracle/ftp/smtp/db/sql_query seulement, historique) — même
        # principe que _SqoopExportConfigDialog, qui les récupère déjà lui-même pour la même raison.
        self._ssh_profiles       = db.get_ssh_profiles()
        self._kerberos_profiles  = db.get_kerberos_profiles()
        self._elevation_profiles = db.get_elevation_profiles()
        self._oracle_profiles    = _.get("oracle_profiles") or []
        self.setWindowTitle("Étape — Import Sqoop (Oracle →)")
        self.setMinimumSize(560, 600)
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        # Même patron de QScrollArea que _SqoopExportConfigDialog — beaucoup de champs (SSH +
        # Kerberos + élévation + Oracle + tables + mappers + conf Sqoop).
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

        root = QVBoxLayout(content); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Import Oracle → Hive/HCatalog (Sqoop, nœud edge)")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)
        self._add_execution_policy_row(form)

        self.cb_ssh = self._profile_row(
            form, "Profil SSH (edge) *",
            self._ssh_profiles, "— Sélectionner un profil SSH —",
            self._new_ssh_profile,
        )
        self.cb_kerberos = self._profile_row(
            form, "Profil Kerberos",
            self._kerberos_profiles, "— Aucun (pas de kinit) —",
            self._new_kerberos_profile,
        )
        self.cb_kerberos.setToolTip(
            "Facultatif — laissez « Aucun » si votre edge ne nécessite pas de ticket Kerberos "
            "pour Sqoop (ex : élévation vers un compte technique ci-dessous à la place)."
        )
        self.cb_elevation = self._profile_row(
            form, "Profil d'élévation (sudo su)",
            self._elevation_profiles, "— Aucune élévation —",
            self._new_elevation_profile,
        )
        self.cb_elevation.setToolTip(
            "Facultatif — bascule vers un utilisateur technique (ex : « nifi ») après connexion "
            "SSH, avant kinit/sqoop, via sudo su. Utile pour les équipes qui passent par un "
            "compte partagé plutôt que par Kerberos."
        )
        self.cb_oracle = self._profile_row(
            form, "Profil Oracle source *",
            self._oracle_profiles, "— Sélectionner un profil Oracle —",
            self._new_oracle_profile,
        )
        self.cb_oracle.setToolTip(
            "Identifiants Oracle chiffrés utilisés pour --connect/--username/--password — "
            "jamais stockés en clair dans la configuration de cette étape."
        )

        self.inp_oracle_table = self._input("ex : xxx.xxxxx")
        form.addRow(self._lbl("Table Oracle source *"), self.inp_oracle_table)
        self.inp_hcat_db = self._input("ex : DD")
        form.addRow(self._lbl("Base HCatalog cible *"), self.inp_hcat_db)
        self.inp_hcat_table = self._input("ex : FINAL_EQUIPEMENT_CLIENT_{yyyyMMdd}")
        form.addRow(self._lbl("Table HCatalog cible *"), self.inp_hcat_table)
        form.addRow("", self._tokens_hint())
        hint_exists = QLabel(
            "La table HCatalog cible doit déjà exister — cette étape ne génère jamais sa "
            "structure (--create-hcatalog-table), même choix que l'étape Chargement base de "
            "données pour ses tables SQL."
        )
        hint_exists.setWordWrap(True)
        hint_exists.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; font-style: italic;")
        form.addRow("", hint_exists)

        self.inp_mappers = QSpinBox()
        self.inp_mappers.setRange(1, 64); self.inp_mappers.setValue(1)
        self.inp_mappers.setStyleSheet(self._spinbox_style())
        self.inp_mappers.setToolTip(
            "Nombre de mappers Sqoop pour paralléliser la LECTURE côté Oracle (sans objet à "
            "l'export, qui écrit dans Oracle sans avoir à en partitionner la lecture). 1 "
            "fonctionne pour n'importe quelle table sans configuration supplémentaire."
        )
        form.addRow(self._lbl("Nombre de mappers"), self.inp_mappers)

        self.inp_split_by = self._input("ex : ID_CLIENT (requis si mappers > 1)")
        self.inp_split_by.setToolTip(
            "Colonne utilisée par Sqoop pour répartir les lignes entre mappers — obligatoire "
            "dès que le nombre de mappers dépasse 1, sans effet sinon."
        )
        self._row_split_by = self._lbl("Colonne de partitionnement")
        form.addRow(self._row_split_by, self.inp_split_by)

        def _toggle_split_by(value):
            self._row_split_by.setVisible(value > 1)
            self.inp_split_by.setVisible(value > 1)
        self.inp_mappers.valueChanged.connect(_toggle_split_by)
        _toggle_split_by(self.inp_mappers.value())

        root.addLayout(form)

        conf_lbl = QLabel("Options Sqoop additionnelles :")
        conf_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        root.addWidget(conf_lbl)
        self.txt_sqoop_conf = QPlainTextEdit()
        self.txt_sqoop_conf.setFont(QFont(FONT_MONO, 11))
        self.txt_sqoop_conf.setPlaceholderText("-D mapreduce.job.queuename=default")
        self.txt_sqoop_conf.setToolTip(
            "Options supplémentaires ajoutées telles quelles à la fin de la commande "
            "sqoop import (allocation de ressources YARN, etc.)."
        )
        self.txt_sqoop_conf.setFixedHeight(80)
        self.txt_sqoop_conf.setStyleSheet(
            f"background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px; padding: 6px;"
        )
        root.addWidget(self.txt_sqoop_conf)
        conf_hint = QLabel(
            "Fourni par l'équipe Big Data — propre à cette étape, indépendant des profils de "
            "connexion (peut changer sans toucher aux identifiants)."
        )
        conf_hint.setWordWrap(True)
        conf_hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; font-style: italic;")
        root.addWidget(conf_hint)

        root.addStretch()

        footer = QVBoxLayout()
        footer.setContentsMargins(28, 0, 28, 20)
        self._buttons(footer)
        outer.addLayout(footer)

    def _new_ssh_profile(self, cb: QComboBox):
        from ui.dialogs import SshProfileDialog
        from database import db_manager as db
        if SshProfileDialog(self).exec():
            self._ssh_profiles = db.get_ssh_profiles()
            cb.clear(); cb.addItem("— Sélectionner un profil SSH —", None)
            for p in self._ssh_profiles: cb.addItem(p.name, p.id)
            cb.setCurrentIndex(cb.count() - 1)

    def _new_kerberos_profile(self, cb: QComboBox):
        from ui.dialogs import KerberosProfileDialog
        from database import db_manager as db
        if KerberosProfileDialog(self).exec():
            self._kerberos_profiles = db.get_kerberos_profiles()
            cb.clear(); cb.addItem("— Sélectionner un profil Kerberos —", None)
            for p in self._kerberos_profiles: cb.addItem(p.name, p.id)
            cb.setCurrentIndex(cb.count() - 1)

    def _new_elevation_profile(self, cb: QComboBox):
        from ui.dialogs import ElevationProfileDialog
        from database import db_manager as db
        if ElevationProfileDialog(self).exec():
            self._elevation_profiles = db.get_elevation_profiles()
            cb.clear(); cb.addItem("— Aucune élévation —", None)
            for p in self._elevation_profiles: cb.addItem(p.name, p.id)
            cb.setCurrentIndex(cb.count() - 1)

    def _new_oracle_profile(self, cb: QComboBox):
        from ui.dialogs import OracleDialog
        from database import db_manager as db
        if OracleDialog(self).exec():
            self._oracle_profiles = db.get_oracle_profiles()
            cb.clear(); cb.addItem("— Sélectionner un profil Oracle —", None)
            for p in self._oracle_profiles: cb.addItem(p.name, p.id)
            cb.setCurrentIndex(cb.count() - 1)

    def _prefill(self):
        c = self._config
        self._set_combo(self.cb_ssh, c.get("edge_profile_id"))
        self._set_combo(self.cb_kerberos, c.get("kerberos_profile_id"))
        self._set_combo(self.cb_elevation, c.get("elevation_profile_id"))
        self._set_combo(self.cb_oracle, c.get("oracle_profile_id"))
        self.inp_oracle_table.setText(c.get("oracle_table", ""))
        self.inp_hcat_db.setText(c.get("hcatalog_database", ""))
        self.inp_hcat_table.setText(c.get("hcatalog_table", ""))
        self.inp_mappers.setValue(int(c.get("num_mappers") or 1))
        self.inp_split_by.setText(c.get("split_by_column", ""))
        self.txt_sqoop_conf.setPlainText(c.get("sqoop_conf", ""))

    def _collect_config(self) -> dict:
        return {
            "edge_profile_id":      self.cb_ssh.currentData(),
            "kerberos_profile_id":  self.cb_kerberos.currentData(),
            "elevation_profile_id": self.cb_elevation.currentData(),
            "oracle_profile_id":    self.cb_oracle.currentData(),
            "oracle_table":        self.inp_oracle_table.text().strip(),
            "hcatalog_database":   self.inp_hcat_db.text().strip(),
            "hcatalog_table":      self.inp_hcat_table.text().strip(),
            "num_mappers":         self.inp_mappers.value(),
            "split_by_column":     self.inp_split_by.text().strip(),
            "sqoop_conf":          self.txt_sqoop_conf.toPlainText().strip(),
        }

    def _on_ok(self):
        if not self.cb_ssh.currentData():
            QMessageBox.warning(self, "Champ requis", "Sélectionner un profil SSH.")
            return
        if not self.cb_oracle.currentData():
            QMessageBox.warning(self, "Champ requis", "Sélectionner un profil Oracle.")
            return
        if not self.inp_oracle_table.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir la table Oracle source.")
            return
        if not self.inp_hcat_db.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir la base HCatalog cible.")
            return
        if not self.inp_hcat_table.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir la table HCatalog cible.")
            return
        if self.inp_mappers.value() > 1 and not self.inp_split_by.text().strip():
            QMessageBox.warning(
                self, "Champ requis",
                "Saisir la colonne de partitionnement (« split-by ») — requise dès que le "
                "nombre de mappers dépasse 1.",
            )
            return
        self.accept()
