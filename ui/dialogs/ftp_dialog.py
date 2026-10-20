"""
DataScheduler — ui/dialogs/ftp_dialog.py
Dialogue de création / édition d'un profil FTP/FTPS/SFTP.
"""

from PySide6.QtWidgets import (
    QComboBox, QDialog, QVBoxLayout, QFormLayout, QLabel,
    QLineEdit, QSpinBox, QFrame,
)
from PySide6.QtCore import Qt, QThread, Signal
from ui.styles import COLORS, DIALOG_STYLE
from ._profile_dialog_chrome import build_header, make_test_banner_container, test_result_title, build_footer


# ──────────────────────────────────────────────
#  DIALOGUE : PROFIL FTP
# ──────────────────────────────────────────────

class FtpTestThread(QThread):
    result_ready = Signal(bool, str)   # success, message

    def __init__(self, config):
        super().__init__()
        self.config = config

    def run(self):
        from core.ftp import FtpUploader
        uploader = FtpUploader(self.config)
        r = uploader.test_connection()
        self.result_ready.emit(r.success, r.message)


class FtpDialog(QDialog):
    """Création / édition d'un profil FTP/FTPS/SFTP."""

    PROTOCOLS = [("FTP", "FTP"), ("FTPS (TLS explicite)", "FTPS"), ("SFTP (SSH)", "SFTP")]

    def __init__(self, parent=None, profile=None):
        super().__init__(parent)
        self._profile     = profile
        self._test_thread = None
        self.setWindowTitle("Profil FTP" if profile is None else "Modifier le profil FTP")
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

        title = self._profile.name if self._profile else "Connexion FTP / FTPS / SFTP"
        root.addWidget(build_header("ftp", title, editing=self._profile is not None))

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.inp_name = self._input("ex : FTP_FINANCE")
        self.inp_host = self._input("ex : ftp.company.com")

        self.inp_port = QSpinBox()
        self.inp_port.setRange(1, 65535)
        self.inp_port.setValue(21)
        self.inp_port.setStyleSheet(self._input_style())
        self.inp_port.setFixedWidth(100)

        self.cb_protocol = QComboBox()
        for label, val in self.PROTOCOLS:
            self.cb_protocol.addItem(label, val)
        self.cb_protocol.setStyleSheet(self._combo_style())
        self.cb_protocol.currentIndexChanged.connect(self._on_protocol_changed)

        self.inp_user = self._input("ex : finance_usr")
        self.inp_pass = self._input("••••••••", password=True)

        form.addRow(self._label("Nom du profil *"), self.inp_name)
        form.addRow(self._label("Hôte *"),          self.inp_host)
        form.addRow(self._label("Port"),             self.inp_port)
        form.addRow(self._label("Protocole"),        self.cb_protocol)
        form.addRow(self._label("Utilisateur *"),    self.inp_user)
        form.addRow(self._label("Mot de passe *"),   self.inp_pass)
        root.addLayout(form)

        banner_container, self._set_banner = make_test_banner_container()
        root.addWidget(banner_container)
        root.addWidget(self._sep())

        footer, self.btn_test, self.btn_cancel, self.btn_save = build_footer(
            "⚡  Tester la connexion", self._on_test, self.reject, self._on_save)
        root.addLayout(footer)

    # ── Logique ──────────────────────────────

    def _on_protocol_changed(self, _):
        proto = self.cb_protocol.currentData()
        self.inp_port.setValue(22 if proto == "SFTP" else 21)

    def _on_test(self):
        config = self._build_config()
        if config is None:
            return
        self.btn_test.setEnabled(False)
        self._set_banner("info", "Connexion en cours…")
        self._test_thread = FtpTestThread(config)
        self._test_thread.result_ready.connect(self._on_test_result)
        self._test_thread.start()

    def _on_test_result(self, success: bool, message: str):
        self.btn_test.setEnabled(True)
        self._set_banner("success" if success else "danger", test_result_title(success), message)

        if self._profile:
            from database import db_manager as db
            db.record_profile_test_result("ftp", self._profile.id, success)

    def _on_save(self):
        if not self._validate():
            return
        from database import db_manager as db
        name     = self.inp_name.text().strip()
        host     = self.inp_host.text().strip()
        port     = self.inp_port.value()
        user     = self.inp_user.text().strip()
        pwd      = self.inp_pass.text().strip()
        protocol = self.cb_protocol.currentData()

        if self._profile:
            db.update_ftp_profile(self._profile.id, name=name, host=host, port=port,
                                  username=user, password=pwd or None, protocol=protocol)
        else:
            db.create_ftp_profile(name=name, host=host, port=port,
                                  username=user, password=pwd, protocol=protocol)
        self.accept()

    def _validate(self) -> bool:
        required = [(self.inp_name, "Nom"), (self.inp_host, "Hôte"), (self.inp_user, "Utilisateur")]
        if self._profile is None:
            required.append((self.inp_pass, "Mot de passe"))
        for inp, label in required:
            if not inp.text().strip():
                inp.setStyleSheet(self._input_style(error=True))
                inp.setPlaceholderText(f"{label} requis")
                inp.setFocus()
                return False
        return True

    def _build_config(self):
        from core.ftp import FtpConfig
        from database import crypto
        host = self.inp_host.text().strip()
        user = self.inp_user.text().strip()
        pwd  = self.inp_pass.text().strip()
        if not pwd and self._profile:
            pwd = crypto.decrypt(self._profile.password)
        if not host or not user or not pwd:
            self._set_banner("warning", "Remplir Hôte / Utilisateur / Mot de passe")
            return None
        return FtpConfig(
            host=host, port=self.inp_port.value(),
            username=user, password=pwd,
            protocol=self.cb_protocol.currentData(),
        )

    def _fill_fields(self, profile):
        self.inp_name.setText(profile.name)
        self.inp_host.setText(profile.host)
        self.inp_port.setValue(profile.port)
        self.inp_user.setText(profile.username)
        self.inp_pass.setPlaceholderText("•••••••• (laisser vide pour conserver)")
        proto = _status_str(profile.protocol) if hasattr(profile.protocol, 'value') else str(profile.protocol)
        idx = self.cb_protocol.findData(proto)
        if idx >= 0:
            self.cb_protocol.setCurrentIndex(idx)

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

    def _combo_style(self) -> str:
        return f"""
            QComboBox {{
                background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']};
                border-radius: 4px; padding: 6px 10px;
                color: {COLORS['text_main']}; font-size: 13px;
            }}
            QComboBox:focus {{ border-color: {COLORS['accent']}; }}
            QComboBox::drop-down {{ border: none; padding-right: 8px; }}
            QComboBox QAbstractItemView {{
                background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']};
                selection-background-color: {COLORS['bg_active']}; color: {COLORS['text_main']};
            }}
        """

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        return lbl

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f


def _status_str(val) -> str:
    return val.value if hasattr(val, "value") else str(val or "")
