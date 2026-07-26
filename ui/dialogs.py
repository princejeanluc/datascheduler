"""
DataScheduler — ui/dialogs/oracle_dialog.py
Dialogue de création / édition d'un profil Oracle.
"""

from PySide6.QtWidgets import (
    QComboBox, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QSpinBox, QRadioButton, QButtonGroup,
    QPushButton, QFrame, QWidget, QSizePolicy, QTextEdit, QPlainTextEdit,
    QScrollArea, QProgressBar, QCheckBox, QMessageBox, QFileDialog,
)
from PySide6.QtCore import Qt, QThread, Signal, QRegularExpression, QTimer
from PySide6.QtGui import QIntValidator, QFont, QSyntaxHighlighter, QTextCharFormat, QColor

from ui.styles import COLORS, DIALOG_STYLE


# ──────────────────────────────────────────────
#  THREAD TEST CONNEXION (non-bloquant)
# ──────────────────────────────────────────────

class OracleTestThread(QThread):
    result_ready = Signal(bool, str, str)   # success, message, version

    def __init__(self, config):
        super().__init__()
        self.config = config

    def run(self):
        try:
            from core.oracle import OracleConnector
            connector = OracleConnector(self.config)
            r = connector.test_connection()
            self.result_ready.emit(r.success, r.message, r.db_version or "")
        except Exception as e:
            self.result_ready.emit(False, f"Erreur inattendue : {e}", "")


# ──────────────────────────────────────────────
#  DIALOGUE
# ──────────────────────────────────────────────

class OracleDialog(QDialog):
    """
    Dialogue de création ou d'édition d'un profil Oracle.

    En création  : OracleDialog(parent)
    En édition   : OracleDialog(parent, profile=<OracleProfile>)
    """

    def __init__(self, parent=None, profile=None):
        super().__init__(parent)
        self._profile     = profile
        self._test_thread = None

        self.setWindowTitle("Profil Oracle" if profile is None else "Modifier le profil Oracle")
        self.setMinimumWidth(480)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()

        if profile:
            self._fill_fields(profile)

    # ── Construction UI ──────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(20)

        # Titre
        title = QLabel("Connexion Oracle")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title)

        sep = self._sep()
        root.addWidget(sep)

        # Formulaire
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.inp_name = self._input("ex : ORACLE_PROD")
        self.inp_host = self._input("ex : 10.10.1.15")

        self.inp_port = QSpinBox()
        self.inp_port.setRange(1, 65535)
        self.inp_port.setValue(1521)
        self.inp_port.setStyleSheet(self._input_style())
        self.inp_port.setFixedWidth(100)

        # Service Name ou SID
        mode_widget = QWidget()
        mode_layout = QHBoxLayout(mode_widget)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(16)

        self.rb_service = QRadioButton("Service Name")
        self.rb_sid     = QRadioButton("SID")
        self.rb_service.setChecked(True)
        for rb in (self.rb_service, self.rb_sid):
            rb.setStyleSheet(f"color: {COLORS['text_main']}; font-size: 13px;")

        self._mode_group = QButtonGroup()
        self._mode_group.addButton(self.rb_service, 0)
        self._mode_group.addButton(self.rb_sid,     1)
        self.rb_service.toggled.connect(self._on_mode_changed)

        mode_layout.addWidget(self.rb_service)
        mode_layout.addWidget(self.rb_sid)
        mode_layout.addStretch()

        self.inp_service = self._input("ex : PROD")
        self.inp_sid     = self._input("ex : ORCLSID")
        self.inp_sid.setVisible(False)

        self.inp_user    = self._input("ex : reporting")
        self.inp_pass    = self._input("••••••••", password=True)

        # Mode d'authentification
        self.cb_auth_mode = QComboBox()
        for label, val in [
            ("Standard (utilisateur normal)", "DEFAULT"),
            ("SYSDBA  — requis pour SYS",      "SYSDBA"),
            ("SYSOPER — administration limitée","SYSOPER"),
        ]:
            self.cb_auth_mode.addItem(label, val)
        self.cb_auth_mode.setStyleSheet(self._combo_style())
        self.cb_auth_mode.currentIndexChanged.connect(self._on_auth_mode_changed)

        # Avertissement SYS
        self.lbl_sys_warn = QLabel(
            "⚠  SYS est un compte d'administration Oracle. "
            "Préférez un compte dédié au reporting si possible."
        )
        self.lbl_sys_warn.setStyleSheet(
            f"color: {COLORS['warning']}; font-size: 11px; font-style: italic;"
        )
        self.lbl_sys_warn.setVisible(False)
        self.lbl_sys_warn.setWordWrap(True)

        form.addRow(self._label("Nom du profil *"), self.inp_name)
        form.addRow(self._label("Hôte *"),          self.inp_host)
        form.addRow(self._label("Port"),             self.inp_port)
        form.addRow(self._label("Mode"),             mode_widget)
        form.addRow(self._label("Service / SID *"),  self.inp_service)
        form.addRow("",                              self.inp_sid)
        form.addRow(self._label("Utilisateur *"),    self.inp_user)
        form.addRow(self._label("Mot de passe *"),   self.inp_pass)
        form.addRow(self._label("Mode auth."),       self.cb_auth_mode)
        form.addRow("",                              self.lbl_sys_warn)
        root.addLayout(form)

        # Zone de test
        root.addWidget(self._build_test_zone())

        sep2 = self._sep()
        root.addWidget(sep2)

        # Boutons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        self.btn_cancel = QPushButton("Annuler")
        self.btn_cancel.setObjectName("secondary")
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton("Enregistrer")
        self.btn_save.setFixedHeight(36)
        self.btn_save.clicked.connect(self._on_save)

        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_save)
        root.addLayout(btn_row)

    def _build_test_zone(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        self.btn_test = QPushButton("⚡  Tester la connexion")
        self.btn_test.setObjectName("secondary")
        self.btn_test.setFixedHeight(32)
        self.btn_test.clicked.connect(self._on_test)

        self.lbl_test_result = QLabel("—")
        self.lbl_test_result.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")

        layout.addWidget(self.btn_test)
        layout.addWidget(self.lbl_test_result, stretch=1)
        return frame

    # ── Logique ──────────────────────────────

    def _on_mode_changed(self, checked):
        is_service = self.rb_service.isChecked()
        self.inp_service.setVisible(is_service)
        self.inp_sid.setVisible(not is_service)

    def _on_auth_mode_changed(self, index: int):
        """Affiche un avertissement si SYSDBA ou SYSOPER est sélectionné."""
        mode = self.cb_auth_mode.currentData()
        self.lbl_sys_warn.setVisible(mode in ("SYSDBA", "SYSOPER"))

    def _on_test(self):
        config = self._build_config()
        if config is None:
            return

        self.btn_test.setEnabled(False)
        self.lbl_test_result.setText("Connexion en cours…")
        self.lbl_test_result.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")

        self._test_thread = OracleTestThread(config)
        self._test_thread.result_ready.connect(self._on_test_result)

        self._test_timeout = QTimer(self)
        self._test_timeout.setSingleShot(True)
        self._test_timeout.timeout.connect(self._on_test_timeout)
        self._test_timeout.start(30_000)   # 30 secondes max

        self._test_thread.start()

    def _on_test_timeout(self):
        if self._test_thread and self._test_thread.isRunning():
            self._test_thread.terminate()
        self._on_test_result(False, "Délai dépassé (30s) — vérifiez l'hôte et le port.", "")

    def _on_test_result(self, success: bool, message: str, version: str):
        if hasattr(self, "_test_timeout"):
            self._test_timeout.stop()
        self.btn_test.setEnabled(True)
        if success:
            txt = f"✅  Connexion réussie — Oracle {version}"
            color = COLORS["success"]
        else:
            txt = f"❌  {message}"
            color = COLORS["danger"]
        self.lbl_test_result.setText(txt)
        self.lbl_test_result.setStyleSheet(f"color: {color}; font-size: 12px;")

    def _on_save(self):
        if not self._validate():
            return

        from database import db_manager as db

        name    = self.inp_name.text().strip()
        host    = self.inp_host.text().strip()
        port    = self.inp_port.value()
        user    = self.inp_user.text().strip()
        pwd     = self.inp_pass.text().strip()
        service = self.inp_service.text().strip() if self.rb_service.isChecked() else None
        sid     = self.inp_sid.text().strip()     if self.rb_sid.isChecked()     else None

        if self._profile:
            # Mise à jour — mot de passe vide = conserver l'existant sans le toucher
            db.update_oracle_profile(
                self._profile.id,
                name=name, host=host, port=port,
                username=user, password=pwd or None,
                service_name=service, sid=sid,
                auth_mode=self.cb_auth_mode.currentData(),
            )
        else:
            db.create_oracle_profile(
                name=name, host=host, port=port,
                username=user, password=pwd,
                service_name=service, sid=sid,
                auth_mode=self.cb_auth_mode.currentData(),
            )

        self.accept()

    def _validate(self) -> bool:
        required = [
            (self.inp_name, "Nom du profil"),
            (self.inp_host, "Hôte"),
            (self.inp_user, "Utilisateur"),
        ]
        # Le mot de passe n'est obligatoire qu'à la création — en édition, un champ
        # vide signifie "conserver le mot de passe existant".
        if self._profile is None:
            required.append((self.inp_pass, "Mot de passe"))
        for inp, label in required:
            if not inp.text().strip():
                self._flash_error(inp, f"{label} requis")
                return False

        if self.rb_service.isChecked() and not self.inp_service.text().strip():
            self._flash_error(self.inp_service, "Service Name requis")
            return False
        if self.rb_sid.isChecked() and not self.inp_sid.text().strip():
            self._flash_error(self.inp_sid, "SID requis")
            return False
        return True

    def _flash_error(self, widget, msg: str):
        widget.setStyleSheet(self._input_style(error=True))
        widget.setPlaceholderText(msg)
        widget.setFocus()

    def _build_config(self):
        """Construit un OracleConfig depuis les champs — None si incomplet."""
        from core.oracle import OracleConfig
        from database import crypto
        host = self.inp_host.text().strip()
        user = self.inp_user.text().strip()
        pwd  = self.inp_pass.text().strip()
        if not pwd and self._profile:
            # Champ laissé vide en édition : on teste avec le mot de passe déjà enregistré.
            pwd = crypto.decrypt(self._profile.password)
        if not host or not user or not pwd:
            self.lbl_test_result.setText("⚠  Remplir Hôte / Utilisateur / Mot de passe")
            self.lbl_test_result.setStyleSheet(f"color: {COLORS['warning']}; font-size: 12px;")
            return None
        service = self.inp_service.text().strip() if self.rb_service.isChecked() else None
        sid     = self.inp_sid.text().strip()     if self.rb_sid.isChecked()     else None
        return OracleConfig(
            host=host, port=self.inp_port.value(),
            username=user, password=pwd,
            service_name=service, sid=sid,
            auth_mode=self.cb_auth_mode.currentData(),
        )

    def _fill_fields(self, profile):
        self.inp_name.setText(profile.name)
        self.inp_host.setText(profile.host)
        self.inp_port.setValue(profile.port)
        self.inp_user.setText(profile.username)
        self.inp_pass.setPlaceholderText("•••••••• (laisser vide pour conserver)")
        if profile.service_name:
            self.rb_service.setChecked(True)
            self.inp_service.setText(profile.service_name)
        elif profile.sid:
            self.rb_sid.setChecked(True)
            self.inp_sid.setText(profile.sid)
        # Mode auth
        mode = getattr(profile, "auth_mode", "DEFAULT") or "DEFAULT"
        idx  = self.cb_auth_mode.findData(mode)
        if idx >= 0:
            self.cb_auth_mode.setCurrentIndex(idx)

    # ── Helpers visuels ──────────────────────

    def _input(self, placeholder="", password=False) -> QLineEdit:
        w = QLineEdit()
        w.setPlaceholderText(placeholder)
        w.setFixedHeight(34)
        if password:
            w.setEchoMode(QLineEdit.Password)
        w.setStyleSheet(self._input_style())
        return w

    def _combo_style(self) -> str:
        return f"""
            QComboBox {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 5px;
                padding: 6px 10px;
                color: {COLORS['text_main']};
                font-size: 13px;
            }}
            QComboBox:focus {{
                border-color: {COLORS['accent']};
            }}
            QComboBox::drop-down {{
                border: none;
                padding-right: 8px;
            }}
            QComboBox QAbstractItemView {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                selection-background-color: {COLORS['bg_active']};
                color: {COLORS['text_main']};
            }}
        """

    def _input_style(self, error=False) -> str:
        border = COLORS["danger"] if error else COLORS["border"]
        return f"""
            QLineEdit, QSpinBox {{
                background: {COLORS['bg_card']};
                border: 1px solid {border};
                border-radius: 5px;
                padding: 6px 10px;
                color: {COLORS['text_main']};
                font-size: 13px;
            }}
            QLineEdit:focus, QSpinBox:focus {{
                border-color: {COLORS['accent']};
            }}
        """

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        return lbl

    def _sep(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f


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

        title = QLabel("Connexion FTP / FTPS / SFTP")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title)
        root.addWidget(self._sep())

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

        self.inp_remote_dir = self._input("ex : /export/data/  (optionnel)")

        form.addRow(self._label("Nom du profil *"), self.inp_name)
        form.addRow(self._label("Hôte *"),          self.inp_host)
        form.addRow(self._label("Port"),             self.inp_port)
        form.addRow(self._label("Protocole"),        self.cb_protocol)
        form.addRow(self._label("Utilisateur *"),    self.inp_user)
        form.addRow(self._label("Mot de passe *"),   self.inp_pass)
        form.addRow(self._label("Dossier distant"),  self.inp_remote_dir)
        root.addLayout(form)

        root.addWidget(self._build_test_zone())
        root.addWidget(self._sep())

        btn_row = QHBoxLayout(); btn_row.setSpacing(10); btn_row.addStretch()
        self.btn_cancel = QPushButton("Annuler"); self.btn_cancel.setObjectName("secondary")
        self.btn_cancel.setFixedHeight(36); self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("Enregistrer")
        self.btn_save.setFixedHeight(36); self.btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self.btn_cancel); btn_row.addWidget(self.btn_save)
        root.addLayout(btn_row)

    def _build_test_zone(self) -> QFrame:
        frame = QFrame(); frame.setObjectName("card")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 10); layout.setSpacing(12)
        self.btn_test = QPushButton("⚡  Tester la connexion")
        self.btn_test.setObjectName("secondary"); self.btn_test.setFixedHeight(32)
        self.btn_test.clicked.connect(self._on_test)
        self.lbl_test_result = QLabel("—")
        self.lbl_test_result.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
        layout.addWidget(self.btn_test); layout.addWidget(self.lbl_test_result, stretch=1)
        return frame

    # ── Logique ──────────────────────────────

    def _on_protocol_changed(self, _):
        proto = self.cb_protocol.currentData()
        self.inp_port.setValue(22 if proto == "SFTP" else 21)

    def _on_test(self):
        config = self._build_config()
        if config is None:
            return
        self.btn_test.setEnabled(False)
        self.lbl_test_result.setText("Connexion en cours…")
        self.lbl_test_result.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
        self._test_thread = FtpTestThread(config)
        self._test_thread.result_ready.connect(self._on_test_result)
        self._test_thread.start()

    def _on_test_result(self, success: bool, message: str):
        self.btn_test.setEnabled(True)
        if success:
            txt   = f"✅  {message}"
            color = COLORS["success"]
        else:
            txt   = f"❌  {message}"
            color = COLORS["danger"]
        self.lbl_test_result.setText(txt)
        self.lbl_test_result.setStyleSheet(f"color: {color}; font-size: 12px;")

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
            self.lbl_test_result.setText("⚠  Remplir Hôte / Utilisateur / Mot de passe")
            self.lbl_test_result.setStyleSheet(f"color: {COLORS['warning']}; font-size: 12px;")
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

        title = QLabel("Connexion SMTP")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title)
        root.addWidget(self._sep())

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

        root.addWidget(self._build_test_zone())
        root.addWidget(self._sep())

        btn_row = QHBoxLayout(); btn_row.setSpacing(10); btn_row.addStretch()
        self.btn_cancel = QPushButton("Annuler"); self.btn_cancel.setObjectName("secondary")
        self.btn_cancel.setFixedHeight(36); self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("Enregistrer")
        self.btn_save.setFixedHeight(36); self.btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self.btn_cancel); btn_row.addWidget(self.btn_save)
        root.addLayout(btn_row)

    def _build_test_zone(self) -> QFrame:
        frame = QFrame(); frame.setObjectName("card")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 10); layout.setSpacing(12)
        self.btn_test = QPushButton("⚡  Tester la connexion")
        self.btn_test.setObjectName("secondary"); self.btn_test.setFixedHeight(32)
        self.btn_test.clicked.connect(self._on_test)
        self.lbl_test_result = QLabel("—")
        self.lbl_test_result.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
        layout.addWidget(self.btn_test); layout.addWidget(self.lbl_test_result, stretch=1)
        return frame

    # ── Logique ──────────────────────────────

    def _on_test(self):
        config = self._build_config()
        if config is None:
            return
        self.btn_test.setEnabled(False)
        self.lbl_test_result.setText("Connexion en cours…")
        self.lbl_test_result.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
        self._test_thread = SmtpTestThread(config)
        self._test_thread.result_ready.connect(self._on_test_result)
        self._test_thread.start()

    def _on_test_result(self, success: bool, message: str):
        self.btn_test.setEnabled(True)
        if success:
            txt   = f"✅  {message}"
            color = COLORS["success"]
        else:
            txt   = f"❌  {message}"
            color = COLORS["danger"]
        self.lbl_test_result.setText(txt)
        self.lbl_test_result.setStyleSheet(f"color: {color}; font-size: 12px;")

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
            self.lbl_test_result.setText("⚠  Remplir Hôte / Adresse expéditeur")
            self.lbl_test_result.setStyleSheet(f"color: {COLORS['warning']}; font-size: 12px;")
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


# ──────────────────────────────────────────────
#  DIALOGUE : CHOIX DU MOTEUR DE BASE DE DONNÉES
# ──────────────────────────────────────────────

DB_TYPE_META = {
    "ORACLE":     {"label": "Oracle",     "color": "#f80000"},
    "MYSQL":      {"label": "MySQL",      "color": "#00758f"},
    "POSTGRESQL": {"label": "PostgreSQL", "color": "#336791"},
    "SQLSERVER":  {"label": "SQL Server", "color": "#a41e22"},
}


class DbTypeChooserDialog(QDialog):
    """Dialogue de sélection du moteur avant de créer un profil de base de données."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.chosen_type: str = ""
        self.setWindowTitle("Nouveau profil de base de données")
        self.setFixedWidth(420)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)

        title = QLabel("Choisir le moteur de base de données")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title)
        root.addWidget(self._sep())

        for db_type, meta in DB_TYPE_META.items():
            btn_row = QFrame()
            btn_row.setCursor(Qt.PointingHandCursor)
            btn_row.setStyleSheet(
                f"QFrame {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
                f"border-radius: 6px; }}"
                f"QFrame:hover {{ border-color: {meta['color']}; background: {meta['color']}11; }}"
            )
            hl = QHBoxLayout(btn_row); hl.setContentsMargins(14, 10, 14, 10); hl.setSpacing(14)
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {meta['color']}; font-size: 18px; background: transparent; border: none;")
            dot.setFixedWidth(20)
            lbl = QLabel(meta["label"])
            lbl.setStyleSheet(
                f"color: {COLORS['text_main']}; font-size: 13px; font-weight: 600; "
                f"background: transparent; border: none;"
            )
            hl.addWidget(dot); hl.addWidget(lbl, stretch=1)
            btn_row.mouseReleaseEvent = lambda _, t=db_type: self._choose(t)
            root.addWidget(btn_row)

        root.addSpacing(6)
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(34); btn_cancel.clicked.connect(self.reject)
        root.addWidget(btn_cancel, alignment=Qt.AlignRight)

    def _choose(self, db_type: str):
        self.chosen_type = db_type
        self.accept()

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f


# ──────────────────────────────────────────────
#  THREAD TEST CONNEXION BASE DE DONNÉES (non-bloquant)
# ──────────────────────────────────────────────

class DatabaseProfileTestThread(QThread):
    result_ready = Signal(bool, str)   # success, message

    def __init__(self, config):
        super().__init__()
        self.config = config

    def run(self):
        from core.sql_db import SqlConnector
        connector = SqlConnector(self.config)
        r = connector.test_connection()
        self.result_ready.emit(r.success, r.message)


# ──────────────────────────────────────────────
#  DIALOGUE : PROFIL BASE DE DONNÉES (MySQL / PostgreSQL / SQL Server)
# ──────────────────────────────────────────────

class DatabaseProfileDialog(QDialog):
    """Création / édition d'un profil de base de données non-Oracle."""

    DEFAULT_PORTS = {"MYSQL": 3306, "POSTGRESQL": 5432, "SQLSERVER": 1433}
    TYPE_LABELS   = {"MYSQL": "MySQL", "POSTGRESQL": "PostgreSQL", "SQLSERVER": "SQL Server"}

    def __init__(self, parent=None, db_type: str = "MYSQL", profile=None):
        super().__init__(parent)
        self._profile = profile
        self._db_type = profile.db_type if profile else db_type
        if hasattr(self._db_type, "value"):
            self._db_type = self._db_type.value
        self._test_thread = None
        label = self.TYPE_LABELS.get(self._db_type, self._db_type)
        self.setWindowTitle(f"Profil {label}" if profile is None else f"Modifier le profil {label}")
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

        label = self.TYPE_LABELS.get(self._db_type, self._db_type)
        title = QLabel(f"Connexion {label}")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title)
        root.addWidget(self._sep())

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.inp_name = self._input(f"ex : {label.upper()}_PROD")
        self.inp_host = self._input("ex : db.company.com")

        self.inp_port = QSpinBox()
        self.inp_port.setRange(1, 65535)
        self.inp_port.setValue(self.DEFAULT_PORTS.get(self._db_type, 1433))
        self.inp_port.setStyleSheet(self._input_style())
        self.inp_port.setFixedWidth(100)

        self.inp_user     = self._input("ex : app_user")
        self.inp_pass     = self._input("••••••••", password=True)
        self.inp_database = self._input("ex : ma_base (optionnel)")

        form.addRow(self._label("Nom du profil *"), self.inp_name)
        form.addRow(self._label("Hôte *"),          self.inp_host)
        form.addRow(self._label("Port"),             self.inp_port)
        form.addRow(self._label("Utilisateur *"),    self.inp_user)
        form.addRow(self._label("Mot de passe *"),   self.inp_pass)
        form.addRow(self._label("Base / schéma"),    self.inp_database)

        self.chk_encrypt = None
        self.chk_trust_cert = None
        if self._db_type == "SQLSERVER":
            self.chk_encrypt = QCheckBox("Chiffrer la connexion (Encrypt)")
            self.chk_encrypt.setChecked(True)
            self.chk_encrypt.setStyleSheet(f"color: {COLORS['text_main']};")
            self.chk_trust_cert = QCheckBox("Faire confiance au certificat serveur (TrustServerCertificate)")
            self.chk_trust_cert.setStyleSheet(f"color: {COLORS['text_main']};")
            form.addRow("", self.chk_encrypt)
            form.addRow("", self.chk_trust_cert)

        root.addLayout(form)
        root.addWidget(self._build_test_zone())
        root.addWidget(self._sep())

        btn_row = QHBoxLayout(); btn_row.setSpacing(10); btn_row.addStretch()
        self.btn_cancel = QPushButton("Annuler"); self.btn_cancel.setObjectName("secondary")
        self.btn_cancel.setFixedHeight(36); self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("Enregistrer")
        self.btn_save.setFixedHeight(36); self.btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self.btn_cancel); btn_row.addWidget(self.btn_save)
        root.addLayout(btn_row)

    def _build_test_zone(self) -> QFrame:
        frame = QFrame(); frame.setObjectName("card")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 10); layout.setSpacing(12)
        self.btn_test = QPushButton("⚡  Tester la connexion")
        self.btn_test.setObjectName("secondary"); self.btn_test.setFixedHeight(32)
        self.btn_test.clicked.connect(self._on_test)
        self.lbl_test_result = QLabel("—")
        self.lbl_test_result.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
        layout.addWidget(self.btn_test); layout.addWidget(self.lbl_test_result, stretch=1)
        return frame

    # ── Logique ──────────────────────────────

    def _on_test(self):
        config = self._build_config()
        if config is None:
            return
        self.btn_test.setEnabled(False)
        self.lbl_test_result.setText("Connexion en cours…")
        self.lbl_test_result.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
        self._test_thread = DatabaseProfileTestThread(config)
        self._test_thread.result_ready.connect(self._on_test_result)
        self._test_thread.start()

    def _on_test_result(self, success: bool, message: str):
        self.btn_test.setEnabled(True)
        if success:
            txt   = f"✅  {message}"
            color = COLORS["success"]
        else:
            txt   = f"❌  {message}"
            color = COLORS["danger"]
        self.lbl_test_result.setText(txt)
        self.lbl_test_result.setStyleSheet(f"color: {color}; font-size: 12px;")

    def _on_save(self):
        if not self._validate():
            return
        from database import db_manager as db
        name = self.inp_name.text().strip()
        host = self.inp_host.text().strip()
        port = self.inp_port.value()
        user = self.inp_user.text().strip()
        pwd  = self.inp_pass.text().strip()
        database_name = self.inp_database.text().strip() or None
        extra = self._collect_extra()

        if self._profile:
            db.update_database_profile(
                self._profile.id,
                name=name, db_type=self._db_type, host=host, port=port,
                username=user, password=pwd or None, database_name=database_name, extra=extra,
            )
        else:
            db.create_database_profile(
                name=name, db_type=self._db_type, host=host, port=port,
                username=user, password=pwd, database_name=database_name, extra=extra,
            )
        self.accept()

    def _collect_extra(self) -> dict:
        if self._db_type == "SQLSERVER":
            return {
                "encrypt": self.chk_encrypt.isChecked(),
                "trust_server_certificate": self.chk_trust_cert.isChecked(),
            }
        return {}

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
        from core.sql_db import SqlDbConfig
        from database import crypto
        host = self.inp_host.text().strip()
        user = self.inp_user.text().strip()
        pwd  = self.inp_pass.text().strip()
        if not pwd and self._profile:
            pwd = crypto.decrypt(self._profile.password)
        if not host or not user or not pwd:
            self.lbl_test_result.setText("⚠  Remplir Hôte / Utilisateur / Mot de passe")
            self.lbl_test_result.setStyleSheet(f"color: {COLORS['warning']}; font-size: 12px;")
            return None
        return SqlDbConfig(
            db_type=self._db_type, host=host, port=self.inp_port.value(),
            username=user, password=pwd,
            database_name=self.inp_database.text().strip() or None,
            extra=self._collect_extra(),
        )

    def _fill_fields(self, profile):
        import json
        self.inp_name.setText(profile.name)
        self.inp_host.setText(profile.host)
        self.inp_port.setValue(profile.port)
        self.inp_user.setText(profile.username)
        self.inp_pass.setPlaceholderText("•••••••• (laisser vide pour conserver)")
        self.inp_database.setText(profile.database_name or "")
        if self._db_type == "SQLSERVER" and profile.extra_json:
            try:
                extra = json.loads(profile.extra_json)
            except ValueError:
                extra = {}
            self.chk_encrypt.setChecked(extra.get("encrypt", True))
            self.chk_trust_cert.setChecked(extra.get("trust_server_certificate", False))

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


# ──────────────────────────────────────────────
#  THREAD + DIALOGUE D'EXÉCUTION EN TEMPS RÉEL
# ──────────────────────────────────────────────

class RunProgressThread(QThread):
    """Lance run_pipeline() dans un thread et émet les signaux vers l'UI."""
    progress_signal = Signal(str, int)   # step, pct
    finished_signal = Signal(object)     # PipelineResult

    def __init__(self, pipeline_id: int):
        super().__init__()
        self.pipeline_id = pipeline_id

    def run(self):
        from core.pipeline import run_pipeline
        result = run_pipeline(
            self.pipeline_id,
            on_progress=lambda step, pct: self.progress_signal.emit(step, pct),
        )
        self.finished_signal.emit(result)


class RunProgressDialog(QDialog):
    """
    Dialogue modal d'exécution d'un pipeline.
    Affiche la progression pas à pas, les logs, et le résultat final.
    Ne peut pas être fermé pendant l'exécution.
    """

    def __init__(self, pipeline_id: int, pipeline_name: str, parent=None):
        super().__init__(parent)
        self._thread = None
        self.setWindowTitle(f"Exécution — {pipeline_name}")
        self.setMinimumSize(500, 340)
        self.setModal(True)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui(pipeline_name)
        self._start(pipeline_id)

    def _build_ui(self, pipeline_name: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        title = QLabel(f"▶  {pipeline_name}")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};"
        )
        root.addWidget(title)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        root.addWidget(sep)

        self.lbl_step = QLabel("Initialisation…")
        self.lbl_step.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
        root.addWidget(self.lbl_step)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {COLORS['bg_card']};
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background: {COLORS['accent']};
                border-radius: 4px;
            }}
        """)
        root.addWidget(self.progress_bar)

        self.log_area = QPlainTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setFont(QFont("Consolas", 10))
        self.log_area.setFixedHeight(140)
        self.log_area.setStyleSheet(
            f"background: {COLORS['bg_main']}; color: {COLORS['text_dim']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px; padding: 6px;"
        )
        root.addWidget(self.log_area)

        self.lbl_result = QLabel("")
        self.lbl_result.setWordWrap(True)
        self.lbl_result.setVisible(False)
        root.addWidget(self.lbl_result)

        root.addStretch()

        btn_row = QHBoxLayout(); btn_row.addStretch()
        self.btn_close = QPushButton("Fermer")
        self.btn_close.setFixedHeight(34)
        self.btn_close.setEnabled(False)
        self.btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_close)
        root.addLayout(btn_row)

    def _start(self, pipeline_id: int):
        self._thread = RunProgressThread(pipeline_id)
        self._thread.progress_signal.connect(self._on_progress)
        self._thread.finished_signal.connect(self._on_finished)
        self._thread.start()

    def _on_progress(self, step: str, pct: int):
        self.lbl_step.setText(step)
        self.progress_bar.setValue(pct)
        self.log_area.appendPlainText(f"  {step}")

    def _on_finished(self, result):
        self.btn_close.setEnabled(True)
        if result.success:
            m, s = divmod(int(result.duration_s), 60)
            dur = f"{m}m {s:02d}s" if m else f"{s}s"
            rows = f"{result.rows_exported:,}".replace(",", " ")
            txt  = f"✅  Succès — {rows} lignes exportées en {dur}"
            color = COLORS["success"]
            self.lbl_step.setText("Terminé ✓")
            self.progress_bar.setValue(100)
        else:
            txt   = f"❌  Erreur : {result.error}"
            color = COLORS["danger"]
            self.lbl_step.setText("Échec")

        self.lbl_result.setText(txt)
        self.lbl_result.setStyleSheet(
            f"color: {color}; font-size: 13px; font-weight: 600;"
        )
        self.lbl_result.setVisible(True)

    def closeEvent(self, event):
        if self._thread and self._thread.isRunning():
            event.ignore()   # bloque la fermeture pendant l'exécution
        else:
            super().closeEvent(event)


# ──────────────────────────────────────────────
#  COLORATION SYNTAXIQUE SQL (simple)
# ──────────────────────────────────────────────

class _SqlHighlighter(QSyntaxHighlighter):
    _KEYWORDS = (
        "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "IN", "IS", "NULL",
        "LIKE", "BETWEEN", "EXISTS", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER",
        "ON", "AS", "GROUP", "BY", "ORDER", "HAVING", "DISTINCT", "UNION",
        "ALL", "INSERT", "INTO", "VALUES", "UPDATE", "SET", "DELETE",
        "CREATE", "ALTER", "DROP", "TABLE", "VIEW", "INDEX", "WITH",
        "CASE", "WHEN", "THEN", "ELSE", "END", "OVER", "PARTITION",
        "ROWNUM", "ROWID", "CONNECT", "START", "PRIOR", "LEVEL",
    )

    def __init__(self, document):
        super().__init__(document)

        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor("#FF7900"))
        kw_fmt.setFontWeight(700)

        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor("#7ec8a4"))

        cmt_fmt = QTextCharFormat()
        cmt_fmt.setForeground(QColor("#666666"))
        cmt_fmt.setFontItalic(True)

        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor("#b5cea8"))

        self._rules = []
        for kw in self._KEYWORDS:
            pat = QRegularExpression(rf"\b{kw}\b", QRegularExpression.CaseInsensitiveOption)
            self._rules.append((pat, kw_fmt))
        self._rules.append((QRegularExpression(r"'[^']*'"), str_fmt))
        self._rules.append((QRegularExpression(r"--[^\n]*"),  cmt_fmt))
        self._rules.append((QRegularExpression(r"\b\d+(\.\d+)?\b"), num_fmt))

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


# ──────────────────────────────────────────────
#  DIALOGUE : REQUÊTE SQL
# ──────────────────────────────────────────────

class SqlQueryDialog(QDialog):
    """Création / édition d'une requête SQL réutilisable."""

    def __init__(self, parent=None, query=None):
        super().__init__(parent)
        self._query = query
        self.setWindowTitle("Requête SQL" if query is None else "Modifier la requête")
        self.setMinimumSize(680, 520)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()
        if query:
            self._fill_fields(query)

    # ── Construction UI ──────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel("Requête SQL")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title)
        root.addWidget(self._sep())

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.inp_name = self._input("ex : REQUETE_VENTES_JOUR")
        self.inp_desc = self._input("Description courte (optionnel)")

        self.cb_oracle = QComboBox()
        self.cb_oracle.setStyleSheet(self._combo_style())
        self._load_oracle_profiles()

        form.addRow(self._label("Nom *"),              self.inp_name)
        form.addRow(self._label("Description"),        self.inp_desc)
        form.addRow(self._label("Profil Oracle"),      self.cb_oracle)
        root.addLayout(form)

        lbl_sql = QLabel("Requête SELECT *")
        lbl_sql.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        root.addWidget(lbl_sql)

        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Consolas", 12))
        self.editor.setStyleSheet(
            f"background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px; padding: 8px;"
        )
        self.editor.setPlaceholderText(
            "SELECT col1, col2\nFROM ma_table\nWHERE condition = :param\nORDER BY col1"
        )
        self._highlighter = _SqlHighlighter(self.editor.document())
        root.addWidget(self.editor, stretch=1)

        root.addWidget(self._sep())

        btn_row = QHBoxLayout(); btn_row.setSpacing(10); btn_row.addStretch()
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(36); btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Enregistrer")
        btn_save.setFixedHeight(36); btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_save)
        root.addLayout(btn_row)

    # ── Logique ──────────────────────────────

    def _load_oracle_profiles(self):
        from database import db_manager as db
        self.cb_oracle.clear()
        self.cb_oracle.addItem("(aucun)", None)
        for p in db.get_oracle_profiles():
            self.cb_oracle.addItem(p.name, p.id)

    def _on_save(self):
        name = self.inp_name.text().strip()
        sql  = self.editor.toPlainText().strip()
        if not name:
            self.inp_name.setStyleSheet(self._input_style(error=True))
            self.inp_name.setFocus()
            return
        if not sql:
            self.editor.setStyleSheet(
                f"background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
                f"border: 2px solid {COLORS['danger']}; border-radius: 4px; padding: 8px;"
            )
            self.editor.setFocus()
            return

        from database import db_manager as db
        desc       = self.inp_desc.text().strip() or None
        oracle_id  = self.cb_oracle.currentData()

        if self._query:
            with db.get_session() as s:
                from database.models import SqlQuery
                q = s.get(SqlQuery, self._query.id)
                q.name              = name
                q.description       = desc
                q.sql_text          = sql
                q.oracle_profile_id = oracle_id
        else:
            db.create_sql_query(name=name, sql_text=sql,
                                description=desc, oracle_profile_id=oracle_id)
        self.accept()

    def _fill_fields(self, query):
        self.inp_name.setText(query.name)
        self.inp_desc.setText(query.description or "")
        self.editor.setPlainText(query.sql_text or "")
        if query.oracle_profile_id:
            idx = self.cb_oracle.findData(query.oracle_profile_id)
            if idx >= 0:
                self.cb_oracle.setCurrentIndex(idx)

    # ── Helpers visuels ──────────────────────

    def _input(self, placeholder="") -> QLineEdit:
        w = QLineEdit(); w.setPlaceholderText(placeholder); w.setFixedHeight(34)
        w.setStyleSheet(self._input_style())
        return w

    def _input_style(self, error=False) -> str:
        border = COLORS["danger"] if error else COLORS["border"]
        return (f"QLineEdit {{ background: {COLORS['bg_card']}; border: 1px solid {border}; "
                f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
                f"QLineEdit:focus {{ border-color: {COLORS['accent']}; }}")

    def _combo_style(self) -> str:
        return (f"QComboBox {{ background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; "
                f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
                f"QComboBox:focus {{ border-color: {COLORS['accent']}; }}"
                f"QComboBox::drop-down {{ border: none; padding-right: 8px; }}"
                f"QComboBox QAbstractItemView {{ background: {COLORS['bg_card']}; "
                f"border: 1px solid {COLORS['border']}; "
                f"selection-background-color: {COLORS['bg_active']}; color: {COLORS['text_main']}; }}")

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        return lbl

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f

# ──────────────────────────────────────────────
#  DIALOGUE : EXPORT DE PIPELINE
# ──────────────────────────────────────────────

class PipelineExportDialog(QDialog):
    """
    Exporte un pipeline vers un fichier .dspipeline (JSON versionné — voir
    database/export_import.py). Le mot de passe chiffre les identifiants des profils
    référencés ; laissé vide, ils sont omis du fichier plutôt que forcés.
    """

    def __init__(self, parent=None, pipeline=None):
        super().__init__(parent)
        self._pipeline = pipeline
        self.setWindowTitle(f"Exporter « {pipeline.name} »")
        self.setMinimumWidth(460)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel(f"Exporter « {self._pipeline.name} »")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title)
        root.addWidget(self._sep())

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.inp_password = QLineEdit()
        self.inp_password.setEchoMode(QLineEdit.Password)
        self.inp_password.setPlaceholderText("Laisser vide pour exporter sans les identifiants")
        self.inp_password.setFixedHeight(34)
        self.inp_password.setStyleSheet(self._input_style())
        form.addRow(self._label("Mot de passe"), self.inp_password)
        root.addLayout(form)

        note = QLabel(
            "Ce mot de passe chiffre les identifiants des profils référencés "
            "(Oracle/FTP/SMTP/base de données) dans le fichier exporté. Laissé vide, le fichier ne "
            "contiendra aucun mot de passe — à ressaisir manuellement après import."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-style: italic;")
        root.addWidget(note)

        root.addWidget(self._sep())
        btn_row = QHBoxLayout(); btn_row.setSpacing(10); btn_row.addStretch()
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(36); btn_cancel.clicked.connect(self.reject)
        btn_export = QPushButton("Exporter…")
        btn_export.setFixedHeight(36); btn_export.clicked.connect(self._on_export)
        btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_export)
        root.addLayout(btn_row)

    def _on_export(self):
        password = self.inp_password.text() or None

        default_name = f"{self._pipeline.name}.dspipeline"
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter le pipeline", default_name,
            "Pipeline DataScheduler (*.dspipeline)",
        )
        if not path:
            return

        from database.export_import import export_pipeline_to_file
        result = export_pipeline_to_file(self._pipeline.id, path, password=password)

        if not result.success:
            QMessageBox.critical(self, "Échec de l'export", result.error or "Erreur inconnue.")
            return

        if result.warnings:
            QMessageBox.warning(
                self, "Export terminé avec avertissements",
                "Le pipeline a été exporté, mais :\n\n"
                + "\n".join(f"• {w}" for w in result.warnings),
            )
        else:
            QMessageBox.information(self, "Export réussi", f"Pipeline exporté vers :\n{path}")

        self.accept()

    def _input_style(self, error=False) -> str:
        border = COLORS["danger"] if error else COLORS["border"]
        return (f"QLineEdit {{ background: {COLORS['bg_card']}; border: 1px solid {border}; "
                f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
                f"QLineEdit:focus {{ border-color: {COLORS['accent']}; }}")

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        return lbl

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f


# ──────────────────────────────────────────────
#  DIALOGUE : MOT DE PASSE D'IMPORT
# ──────────────────────────────────────────────

class PipelineImportPasswordDialog(QDialog):
    """Prompt du mot de passe nécessaire pour déchiffrer un bundle .dspipeline importé."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mot de passe requis")
        self.setMinimumWidth(420)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel("Mot de passe requis")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title)
        root.addWidget(self._sep())

        note = QLabel(
            "Ce fichier contient des identifiants chiffrés. Saisissez le mot de passe utilisé "
            "au moment de l'export pour les déchiffrer."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-style: italic;")
        root.addWidget(note)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.inp_password = QLineEdit()
        self.inp_password.setEchoMode(QLineEdit.Password)
        self.inp_password.setFixedHeight(34)
        self.inp_password.setStyleSheet(self._input_style())
        form.addRow(self._label("Mot de passe"), self.inp_password)
        root.addLayout(form)

        root.addWidget(self._sep())
        btn_row = QHBoxLayout(); btn_row.setSpacing(10); btn_row.addStretch()
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(36); btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Valider")
        btn_ok.setFixedHeight(36); btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_ok)
        root.addLayout(btn_row)

    def password(self) -> str:
        return self.inp_password.text()

    def _input_style(self, error=False) -> str:
        border = COLORS["danger"] if error else COLORS["border"]
        return (f"QLineEdit {{ background: {COLORS['bg_card']}; border: 1px solid {border}; "
                f"border-radius: 4px; padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
                f"QLineEdit:focus {{ border-color: {COLORS['accent']}; }}")

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: 500;")
        return lbl

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f
