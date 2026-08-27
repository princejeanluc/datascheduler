"""
DataScheduler — ui/step_editor/sqoop_export_config_dialog.py
Dialogue de configuration d'une étape SQOOP_EXPORT.
"""

from PySide6.QtWidgets import (
    QVBoxLayout, QLabel, QComboBox, QPlainTextEdit, QMessageBox, QWidget, QScrollArea, QFrame,
)
from PySide6.QtGui import QFont
from ui.styles import COLORS, FONT_MONO
from .base_config_dialog import _BaseStepConfigDialog


class _SqoopExportConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "SQOOP_EXPORT"

    def __init__(self, config: dict, parent=None, label: str = "", **_):
        super().__init__(config, parent, label,
                          retry_count=_.get("retry_count", 0),
                          retry_interval_s=_.get("retry_interval_s", 5),
                          run_always=_.get("run_always", False),
                          timeout_s=_.get("timeout_s", 0))
        from database import db_manager as db
        # ssh_profiles/kerberos_profiles/elevation_profiles ne font pas partie du kwargs partagé
        # de _open_config_dialog() (oracle/ftp/smtp/db/sql_query seulement, historique) — même
        # principe que _SparkSqlConfigDialog, qui les récupère déjà lui-même pour la même raison.
        self._ssh_profiles       = db.get_ssh_profiles()
        self._kerberos_profiles  = db.get_kerberos_profiles()
        self._elevation_profiles = db.get_elevation_profiles()
        self._oracle_profiles    = _.get("oracle_profiles") or []
        self.setWindowTitle("Étape — Export Sqoop (→ Oracle)")
        self.setMinimumSize(560, 560)
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        # Beaucoup de champs (SSH + Kerberos + élévation + Oracle + 3 tables + conf Sqoop) —
        # même patron de QScrollArea que le dialogue Script Python : `root` reste le layout du
        # contenu défilant, Annuler/Valider restent fixes en pied de fenêtre.
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
        title = QLabel("Export Hive/HCatalog → Oracle (Sqoop, nœud edge)")
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
            form, "Profil Oracle cible *",
            self._oracle_profiles, "— Sélectionner un profil Oracle —",
            self._new_oracle_profile,
        )
        self.cb_oracle.setToolTip(
            "Identifiants Oracle chiffrés utilisés pour --connect/--username/--password — "
            "jamais stockés en clair dans la configuration de cette étape."
        )

        self.inp_hcat_db = self._input("ex : DD")
        form.addRow(self._lbl("Base HCatalog source *"), self.inp_hcat_db)
        self.inp_hcat_table = self._input("ex : FINAL_EQUIPEMENT_CLIENT_{yyyyMMdd}")
        form.addRow(self._lbl("Table HCatalog source *"), self.inp_hcat_table)
        self.inp_oracle_table = self._input("ex : xxx.xxxxx")
        form.addRow(self._lbl("Table Oracle cible *"), self.inp_oracle_table)
        form.addRow("", self._tokens_hint())

        root.addLayout(form)

        conf_lbl = QLabel("Options Sqoop additionnelles :")
        conf_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        root.addWidget(conf_lbl)
        self.txt_sqoop_conf = QPlainTextEdit()
        self.txt_sqoop_conf.setFont(QFont(FONT_MONO, 11))
        self.txt_sqoop_conf.setPlaceholderText("-D mapreduce.job.queuename=default --num-mappers 4")
        self.txt_sqoop_conf.setToolTip(
            "Options supplémentaires ajoutées telles quelles à la fin de la commande "
            "sqoop export (allocation de ressources YARN, --num-mappers, etc.)."
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
        self.inp_hcat_db.setText(c.get("hcatalog_database", ""))
        self.inp_hcat_table.setText(c.get("hcatalog_table", ""))
        self.inp_oracle_table.setText(c.get("oracle_table", ""))
        self.txt_sqoop_conf.setPlainText(c.get("sqoop_conf", ""))

    def _collect_config(self) -> dict:
        return {
            "edge_profile_id":      self.cb_ssh.currentData(),
            "kerberos_profile_id":  self.cb_kerberos.currentData(),
            "elevation_profile_id": self.cb_elevation.currentData(),
            "oracle_profile_id":    self.cb_oracle.currentData(),
            "hcatalog_database":   self.inp_hcat_db.text().strip(),
            "hcatalog_table":      self.inp_hcat_table.text().strip(),
            "oracle_table":        self.inp_oracle_table.text().strip(),
            "sqoop_conf":          self.txt_sqoop_conf.toPlainText().strip(),
        }

    def _on_ok(self):
        if not self.cb_ssh.currentData():
            QMessageBox.warning(self, "Champ requis", "Sélectionner un profil SSH.")
            return
        if not self.cb_oracle.currentData():
            QMessageBox.warning(self, "Champ requis", "Sélectionner un profil Oracle.")
            return
        if not self.inp_hcat_db.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir la base HCatalog source.")
            return
        if not self.inp_hcat_table.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir la table HCatalog source.")
            return
        if not self.inp_oracle_table.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir la table Oracle cible.")
            return
        self.accept()
