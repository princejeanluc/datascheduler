"""
DataScheduler — ui/dialogs/smtp_dialog.py
Dialogue de création / édition d'un profil SMTP.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLabel, QLineEdit,
    QSpinBox, QFrame, QCheckBox,
)
from PySide6.QtCore import Qt, QThread, Signal
from ui.styles import COLORS, DIALOG_STYLE
from ._profile_dialog_chrome import build_header, make_test_banner_container, test_result_title, build_footer


# ──────────────────────────────────────────────
#  THREAD TEST CONNEXION SMTP (non-bloquant)
# ──────────────────────────────────────────────

class SmtpTestThread(QThread):
    result_ready = Signal(bool, str)   # success, message

    def __init__(self, config):
        super().__init__()
        self.config = config

    def run(self):
        from core.email import EmailSender
        sender = EmailSender(self.config)
        r = sender.test_connection()
        self.result_ready.emit(r.success, r.message)


# ──────────────────────────────────────────────
#  DIALOGUE : PROFIL SMTP
# ──────────────────────────────────────────────

class SmtpDialog(QDialog):
    """Création / édition d'un profil SMTP."""

    def __init__(self, parent=None, profile=None):
        super().__init__(parent)
        self._profile     = profile
        self._test_thread = None
        self.setWindowTitle("Profil SMTP" if profile is None else "Modifier le profil SMTP")
        self.setMinimumWidth(460)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()
        if profile:
            self._fill_fields(profile)

    # ── Construction UI ──────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(20)

        title = self._profile.name if self._profile else "Connexion SMTP"
        root.addWidget(build_header("smtp", title, editing=self._profile is not None))

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.inp_name = self._input("ex : SMTP_INTERNE")
        self.inp_host = self._input("ex : smtp.company.com")

        self.inp_port = QSpinBox()
        self.inp_port.setRange(1, 65535)
        self.inp_port.setValue(587)
        self.inp_port.setStyleSheet(self._input_style())
        self.inp_port.setFixedWidth(100)

        self.chk_tls = QCheckBox("STARTTLS")
        self.chk_tls.setChecked(True)
        self.chk_tls.setStyleSheet(f"color: {COLORS['text_main']};")

        self.inp_user = self._input("ex : notifications@company.com  (optionnel)")
        self.inp_pass = self._input("••••••••  (optionnel)", password=True)
        self.inp_from = self._input("ex : datascheduler@company.com")

        form.addRow(self._label("Nom du profil *"),  self.inp_name)
        form.addRow(self._label("Hôte *"),           self.inp_host)
        form.addRow(self._label("Port"),              self.inp_port)
        form.addRow(self._label("Sécurité"),          self.chk_tls)
        form.addRow(self._label("Utilisateur"),       self.inp_user)
        form.addRow(self._label("Mot de passe"),      self.inp_pass)
        form.addRow(self._label("Adresse expéditeur *"), self.inp_from)
        root.addLayout(form)

        banner_container, self._set_banner = make_test_banner_container()
        root.addWidget(banner_container)
        root.addWidget(self._sep())

        footer, self.btn_test, self.btn_cancel, self.btn_save = build_footer(
            "⚡  Tester la connexion", self._on_test, self.reject, self._on_save)
        root.addLayout(footer)

    # ── Logique ──────────────────────────────

    def _on_test(self):
        config = self._build_config()
        if config is None:
            return
        self.btn_test.setEnabled(False)
        self._set_banner("info", "Connexion en cours…")
        self._test_thread = SmtpTestThread(config)
        self._test_thread.result_ready.connect(self._on_test_result)
        self._test_thread.start()

    def _on_test_result(self, success: bool, message: str):
        self.btn_test.setEnabled(True)
        self._set_banner("success" if success else "danger", test_result_title(success), message)

        if self._profile:
            from database import db_manager as db
            db.record_profile_test_result("smtp", self._profile.id, success)

    def _on_save(self):
        if not self._validate():
            return
        from database import db_manager as db
        name    = self.inp_name.text().strip()
        host    = self.inp_host.text().strip()
        port    = self.inp_port.value()
        user    = self.inp_user.text().strip() or None
        pwd     = self.inp_pass.text().strip() or None
        use_tls = self.chk_tls.isChecked()
        from_addr = self.inp_from.text().strip()

        if self._profile:
            db.update_smtp_profile(self._profile.id, name=name, host=host, port=port,
                                   from_address=from_addr,
                                   username=user, password=pwd, use_tls=use_tls)
        else:
            db.create_smtp_profile(name=name, host=host, port=port,
                                   from_address=from_addr,
                                   username=user, password=pwd, use_tls=use_tls)
        self.accept()

    def _validate(self) -> bool:
        for inp, label in [(self.inp_name, "Nom"), (self.inp_host, "Hôte"),
                           (self.inp_from, "Adresse expéditeur")]:
            if not inp.text().strip():
                inp.setStyleSheet(self._input_style(error=True))
                inp.setPlaceholderText(f"{label} requis")
                inp.setFocus()
                return False
        return True

    def _build_config(self):
        from core.email import SmtpConfig
        from database import crypto
        host = self.inp_host.text().strip()
        from_addr = self.inp_from.text().strip()
        pwd = self.inp_pass.text().strip()
        if not pwd and self._profile and self._profile.password:
            pwd = crypto.decrypt(self._profile.password)
        if not host or not from_addr:
            self._set_banner("warning", "Remplir Hôte / Adresse expéditeur")
            return None
        return SmtpConfig(
            host=host, port=self.inp_port.value(),
            username=self.inp_user.text().strip() or None,
            password=pwd or None,
            use_tls=self.chk_tls.isChecked(),
            from_address=from_addr,
        )

    def _fill_fields(self, profile):
        self.inp_name.setText(profile.name)
        self.inp_host.setText(profile.host)
        self.inp_port.setValue(profile.port)
        self.inp_user.setText(profile.username or "")
        self.inp_pass.setPlaceholderText("•••••••• (laisser vide pour conserver)" if profile.password else "")
        self.chk_tls.setChecked(bool(profile.use_tls))
        self.inp_from.setText(profile.from_address)

    # ── Helpers visuels ──────────────────────

    def _input(self, placeholder="", password=False) -> QLineEdit:
        w = QLineEdit(); w.setPlaceholderText(placeholder); w.setFixedHeight(34)
        if password:
            w.setEchoMode(QLineEdit.Password)
        w.setStyleSheet(self._input_style())
        return w

    def _input_style(self, error=False) -> str:
        border = COLORS["danger"] if error else COLORS["border"]
        return f"""
            QLineEdit, QSpinBox {{
                background: {COLORS['bg_card']}; border: 1px solid {border};
                border-radius: 4px; padding: 6px 10px;
                color: {COLORS['text_main']}; font-size: 13px;
            }}
            QLineEdit:focus, QSpinBox:focus {{ border-color: {COLORS['accent']}; }}
        """

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        return lbl

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f
