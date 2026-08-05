"""
DataScheduler — ui/step_editor/spark_sql_config_dialog.py
Dialogue de configuration d'une étape SPARK_SQL.
"""

from PySide6.QtWidgets import (
    QVBoxLayout, QLabel, QComboBox, QPlainTextEdit, QCheckBox, QSpinBox, QMessageBox,
)
from PySide6.QtGui import QFont
from ui.styles import COLORS
from .base_config_dialog import _BaseStepConfigDialog


class _SparkSqlConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "SPARK_SQL"

    def __init__(self, config: dict, parent=None, label: str = "", **_):
        super().__init__(config, parent, label,
                          retry_count=_.get("retry_count", 0),
                          run_always=_.get("run_always", False))
        from database import db_manager as db
        # ssh_profiles/kerberos_profiles ne font pas partie du kwargs partagé de
        # _open_config_dialog() (oracle/ftp/smtp/db/sql_query seulement, historique) — pas
        # besoin d'y toucher (ça casserait les dialogues à signature explicite) : ce dialogue
        # les récupère lui-même, même principe que KerberosProfileDialog pour son propre test.
        self._ssh_profiles      = db.get_ssh_profiles()
        self._kerberos_profiles = db.get_kerberos_profiles()
        self._sql_queries       = _.get("sql_queries") or []
        self.setWindowTitle("Étape — Spark SQL")
        self.setMinimumSize(560, 560)
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Requête Spark SQL (nœud edge + Kerberos)")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)
        self._add_execution_policy_row(form)

        self.cb_ssh = self._profile_row(
            form, "Profil SSH *",
            self._ssh_profiles, "— Sélectionner un profil SSH —",
            self._new_ssh_profile,
        )
        self.cb_kerberos = self._profile_row(
            form, "Profil Kerberos *",
            self._kerberos_profiles, "— Sélectionner un profil Kerberos —",
            self._new_kerberos_profile,
        )
        self.cb_query = self._profile_row(
            form, "Requête SQL *",
            self._sql_queries, "— Sélectionner une requête SQL —",
            self._new_sql_query,
        )

        self.inp_timeout = QSpinBox()
        self.inp_timeout.setRange(30, 86400); self.inp_timeout.setValue(3600)
        self.inp_timeout.setSuffix(" s"); self.inp_timeout.setFixedWidth(110)
        self.inp_timeout.setStyleSheet(self._spinbox_style())
        self.inp_timeout.setToolTip(
            "Durée maximale d'exécution côté cluster avant interruption automatique."
        )
        form.addRow(self._lbl("Timeout"), self.inp_timeout)

        self.chk_fetch = QCheckBox("Récupérer le résultat")
        self.chk_fetch.setStyleSheet(f"color: {COLORS['text_main']};")
        self.chk_fetch.setToolTip(
            "Coché : le résultat de la requête est rapatrié comme fichier (CSV-like), "
            "utilisable par les étapes suivantes. Décoché : la requête est exécutée sans "
            "rapatrier de résultat (ex : INSERT, CREATE TABLE AS, rafraîchissement de cache)."
        )
        form.addRow("", self.chk_fetch)

        self.inp_output_name = self._output_name_row(form)
        root.addLayout(form)

        conf_lbl = QLabel("Configuration Spark (--conf ...) :")
        conf_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        root.addWidget(conf_lbl)
        self.txt_spark_conf = QPlainTextEdit()
        self.txt_spark_conf.setFont(QFont("Consolas", 11))
        self.txt_spark_conf.setPlaceholderText(
            '--conf "spark.hadoop.hive.cli.print.header=true" --conf spark.yarn.queue=default '
            '--executor-cores 1 --num-executors 10 --driver-memory 10G --executor-memory 7G'
        )
        self.txt_spark_conf.setFixedHeight(90)
        self.txt_spark_conf.setStyleSheet(
            f"background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px; padding: 6px;"
        )
        root.addWidget(self.txt_spark_conf)
        conf_hint = QLabel(
            "Fourni par l'équipe Big Data — propre à cette étape, indépendant des profils de "
            "connexion (peut changer sans toucher aux identifiants)."
        )
        conf_hint.setWordWrap(True)
        conf_hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; font-style: italic;")
        root.addWidget(conf_hint)

        def _toggle_output_name(checked):
            self.inp_output_name.setVisible(checked)
            lbl = form.labelForField(self.inp_output_name)
            if lbl:
                lbl.setVisible(checked)
        self.chk_fetch.toggled.connect(_toggle_output_name)
        _toggle_output_name(self.chk_fetch.isChecked())

        root.addStretch()
        self._buttons(root)

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

    def _new_sql_query(self, cb: QComboBox):
        from ui.dialogs import SqlQueryDialog
        from database import db_manager as db
        if SqlQueryDialog(self).exec():
            self._sql_queries = db.get_sql_queries()
            cb.clear(); cb.addItem("— Sélectionner une requête SQL —", None)
            for q in self._sql_queries: cb.addItem(q.name, q.id)
            cb.setCurrentIndex(cb.count() - 1)

    def _prefill(self):
        c = self._config
        self._set_combo(self.cb_ssh, c.get("edge_profile_id"))
        self._set_combo(self.cb_kerberos, c.get("kerberos_profile_id"))
        self._set_combo(self.cb_query, c.get("sql_query_id"))
        self.inp_timeout.setValue(int(c.get("timeout", 3600)))
        self.chk_fetch.setChecked(bool(c.get("fetch_result", False)))
        self.inp_output_name.setText(c.get("output_name", ""))
        self.txt_spark_conf.setPlainText(c.get("spark_conf", ""))

    def _collect_config(self) -> dict:
        return {
            "edge_profile_id":     self.cb_ssh.currentData(),
            "kerberos_profile_id": self.cb_kerberos.currentData(),
            "sql_query_id":        self.cb_query.currentData(),
            "timeout":             self.inp_timeout.value(),
            "fetch_result":        self.chk_fetch.isChecked(),
            "output_name":         self.inp_output_name.text().strip(),
            "spark_conf":          self.txt_spark_conf.toPlainText().strip(),
        }

    def _on_ok(self):
        if not self.cb_ssh.currentData():
            QMessageBox.warning(self, "Champ requis", "Sélectionner un profil SSH.")
            return
        if not self.cb_kerberos.currentData():
            QMessageBox.warning(self, "Champ requis", "Sélectionner un profil Kerberos.")
            return
        if not self.cb_query.currentData():
            QMessageBox.warning(self, "Champ requis", "Sélectionner une requête SQL.")
            return
        self.accept()
