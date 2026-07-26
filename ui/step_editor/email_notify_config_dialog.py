"""
DataScheduler — ui/step_editor/email_notify_config_dialog.py
Dialogue de configuration d'une étape EMAIL_NOTIFY.
"""

from PySide6.QtWidgets import (
    QVBoxLayout, QLabel, QComboBox, QPlainTextEdit, QCheckBox, QMessageBox,
)
from PySide6.QtGui import QFont
from ui.styles import COLORS
from .base_config_dialog import _BaseStepConfigDialog


class _EmailNotifyConfigDialog(_BaseStepConfigDialog):
    STEP_TYPE = "EMAIL_NOTIFY"

    def __init__(self, config: dict, parent=None, label: str = "", **_):
        super().__init__(config, parent, label,
                          retry_count=_.get("retry_count", 0),
                          run_always=_.get("run_always", False))
        self._smtp_profiles = _.get("smtp_profiles") or []
        self._prior_steps   = _.get("prior_steps") or []
        self.setWindowTitle("Étape — Notification email")
        self.setMinimumSize(540, 480)
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 20); root.setSpacing(16)
        title = QLabel("Envoi d'un email de notification")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title); root.addWidget(self._sep())

        form = self._form()
        self._add_label_row(form)
        self._add_execution_policy_row(form)
        self.cb_smtp = self._profile_row(
            form, "Profil SMTP *",
            self._smtp_profiles, "— Sélectionner un profil SMTP —",
            self._new_smtp_profile,
        )
        self.inp_to = self._input("ex : alerte@company.com, autre@company.com")
        form.addRow(self._lbl("Destinataires *"), self.inp_to)

        self.inp_subject = self._input("ex : Pipeline {yyyyMMdd} — {rows_count} lignes")
        form.addRow(self._lbl("Sujet *"), self.inp_subject)
        form.addRow("", self._tokens_hint())
        root.addLayout(form)

        body_lbl = QLabel("Corps du message :")
        body_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        root.addWidget(body_lbl)
        self.txt_body = QPlainTextEdit()
        self.txt_body.setFont(QFont("Consolas", 11))
        self.txt_body.setPlaceholderText("Le pipeline a exporté {rows_count} lignes le {yyyy}-{MM}-{dd}.")
        self.txt_body.setFixedHeight(110)
        self.txt_body.setStyleSheet(
            f"background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px; padding: 6px;"
        )
        root.addWidget(self.txt_body)

        self.chk_attach = QCheckBox("Joindre le fichier produit par le pipeline (si disponible)")
        self.chk_attach.setStyleSheet(f"color: {COLORS['text_main']};")
        root.addWidget(self.chk_attach)

        attach_form = self._form()
        self.cb_source = self._source_row(attach_form, self._prior_steps)
        root.addLayout(attach_form)

        root.addStretch()
        self._buttons(root)

    def _prefill(self):
        c = self._config
        self._set_combo(self.cb_smtp, c.get("smtp_profile_id"))
        self.inp_to.setText(c.get("to", ""))
        self.inp_subject.setText(c.get("subject_tpl", ""))
        self.txt_body.setPlainText(c.get("body_tpl", ""))
        self.chk_attach.setChecked(c.get("attach_output_file", False))
        self._set_combo(self.cb_source, c.get("reads_from_step_key"))

    def _new_smtp_profile(self, cb: QComboBox):
        from ui.dialogs import SmtpDialog
        from database import db_manager as db
        if SmtpDialog(self).exec():
            self._smtp_profiles = db.get_smtp_profiles()
            cb.clear(); cb.addItem("— Sélectionner un profil SMTP —", None)
            for p in self._smtp_profiles: cb.addItem(p.name, p.id)
            cb.setCurrentIndex(cb.count() - 1)

    def _collect_config(self) -> dict:
        return {
            "smtp_profile_id":    self.cb_smtp.currentData(),
            "to":                 self.inp_to.text().strip(),
            "subject_tpl":        self.inp_subject.text().strip(),
            "body_tpl":           self.txt_body.toPlainText(),
            "attach_output_file": self.chk_attach.isChecked(),
            "reads_from_step_key": self.cb_source.currentData(),
        }

    def _on_ok(self):
        if not self.cb_smtp.currentData():
            QMessageBox.warning(self, "Champ requis", "Sélectionner un profil SMTP.")
            return
        if not self.inp_to.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir au moins un destinataire.")
            return
        if not self.inp_subject.text().strip():
            QMessageBox.warning(self, "Champ requis", "Saisir un sujet.")
            return
        self.accept()
