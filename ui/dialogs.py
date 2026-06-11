"""
DataScheduler — ui/dialogs/oracle_dialog.py
Dialogue de création / édition d'un profil Oracle.
"""

from PySide6.QtWidgets import (
    QComboBox, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QSpinBox, QRadioButton, QButtonGroup,
    QPushButton, QFrame, QWidget, QSizePolicy, QTextEdit, QPlainTextEdit,
    QScrollArea, QProgressBar,
)
from PySide6.QtCore import Qt, QThread, Signal, QRegularExpression
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
        from core.oracle import OracleConnector
        connector = OracleConnector(self.config)
        r = connector.test_connection()
        self.result_ready.emit(
            r.success,
            r.message,
            r.db_version or "",
        )


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
        self._test_thread.start()

    def _on_test_result(self, success: bool, message: str, version: str):
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
            # Mise à jour
            with db.get_session() as s:
                from database.models import OracleProfile
                p = s.get(OracleProfile, self._profile.id)
                p.name         = name
                p.host         = host
                p.port         = port
                p.username     = user
                p.password     = pwd
                p.service_name = service
                p.sid          = sid
                p.auth_mode    = self.cb_auth_mode.currentData()
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
            (self.inp_pass, "Mot de passe"),
        ]
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
        host = self.inp_host.text().strip()
        user = self.inp_user.text().strip()
        pwd  = self.inp_pass.text().strip()
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
        self.inp_pass.setText(profile.password)
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
            with db.get_session() as s:
                from database.models import FtpProfile
                p = s.get(FtpProfile, self._profile.id)
                p.name = name; p.host = host; p.port = port
                p.username = user; p.password = pwd; p.protocol = protocol
        else:
            db.create_ftp_profile(name=name, host=host, port=port,
                                  username=user, password=pwd, protocol=protocol)
        self.accept()

    def _validate(self) -> bool:
        for inp, label in [(self.inp_name, "Nom"), (self.inp_host, "Hôte"),
                           (self.inp_user, "Utilisateur"), (self.inp_pass, "Mot de passe")]:
            if not inp.text().strip():
                inp.setStyleSheet(self._input_style(error=True))
                inp.setPlaceholderText(f"{label} requis")
                inp.setFocus()
                return False
        return True

    def _build_config(self):
        from core.ftp import FtpConfig
        host = self.inp_host.text().strip()
        user = self.inp_user.text().strip()
        pwd  = self.inp_pass.text().strip()
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
        self.inp_pass.setText(profile.password)
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
#  DIALOGUE : PIPELINE
# ──────────────────────────────────────────────

class PipelineDialog(QDialog):
    """
    Création / édition d'un pipeline complet.

    Sections :
      1. Informations générales (nom, description)
      2. Source Oracle (profil + requête SQL)
      3. Destination FTP (profil + chemin + nom de fichier)
      4. Planification (fréquence, heure, jour)
    """

    FREQ_LABELS = [
        ("Quotidien",   "DAILY"),
        ("Hebdomadaire","WEEKLY"),
        ("Mensuel",     "MONTHLY"),
        ("Personnalisé","CUSTOM"),
    ]
    DAYS_WEEK  = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
    SEPARATORS = [("; (point-virgule)", ";"), (", (virgule)", ","),
                  ("| (pipe)", "|"), ("\\t (tabulation)", "\t")]
    ENCODINGS  = [("UTF-8", "utf-8"), ("UTF-8 BOM (Excel)", "utf-8-sig"),
                  ("Latin-1", "latin-1"), ("CP1252 (Windows)", "cp1252")]

    def __init__(self, parent=None, pipeline=None):
        super().__init__(parent)
        self._pipeline = pipeline
        self.setWindowTitle("Nouveau pipeline" if pipeline is None else "Modifier le pipeline")
        self.setMinimumSize(560, 680)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()
        if pipeline:
            self._fill_fields(pipeline)

    # ── Construction UI ──────────────────────

    def _build_ui(self):
        # Dialog root: title bar + scroll area + button row
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        title = QLabel("  Configuration du pipeline")
        title.setFixedHeight(48)
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {COLORS['text_main']};"
            f"padding-left: 28px; border-bottom: 1px solid {COLORS['border']};"
            f"background: {COLORS['bg_panel']};"
        )
        root.addWidget(title)

        # Scroll container
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        inner = QWidget()
        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

        # The actual form goes into `inner`
        form_root = QVBoxLayout(inner)
        form_root.setContentsMargins(28, 20, 28, 12)
        form_root.setSpacing(16)

        # ── alias to avoid touching every addWidget call below ──
        # (all subsequent root.addWidget / root.addLayout will target form_root)
        # Keep a reference to the outer dialog layout for the button row
        self._dialog_root = root
        root = form_root   # all subsequent root.addWidget calls build the scrollable form

        # ── Section 1 : infos générales ──
        root.addWidget(self._section_label("① Informations générales"))
        f1 = QFormLayout(); f1.setSpacing(10)
        f1.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f1.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.inp_name = self._input("ex : EXPORT_VENTES_QUOTIDIEN")
        self.inp_desc = self._input("Description optionnelle")
        f1.addRow(self._label("Nom *"),       self.inp_name)
        f1.addRow(self._label("Description"), self.inp_desc)
        root.addLayout(f1)

        root.addWidget(self._sep())

        # ── Section 2 : source Oracle ──
        root.addWidget(self._section_label("② Source Oracle"))
        f2 = QFormLayout(); f2.setSpacing(10)
        f2.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f2.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.cb_oracle = QComboBox(); self.cb_oracle.setStyleSheet(self._combo_style())
        self.cb_query  = QComboBox(); self.cb_query.setStyleSheet(self._combo_style())
        self._load_oracle_profiles()
        self._load_queries()
        self.cb_oracle.currentIndexChanged.connect(self._on_oracle_changed)

        f2.addRow(self._label("Profil Oracle *"),  self.cb_oracle)
        f2.addRow(self._label("Requête SQL *"),    self.cb_query)
        root.addLayout(f2)

        root.addWidget(self._sep())

        # ── Section 3 : destination FTP ──
        root.addWidget(self._section_label("③ Destination FTP"))
        f3 = QFormLayout(); f3.setSpacing(10)
        f3.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f3.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.cb_ftp           = QComboBox(); self.cb_ftp.setStyleSheet(self._combo_style())
        self.inp_remote_path  = self._input("ex : /export/{yyyy}/{MM}/")
        self.inp_filename     = self._input("ex : ventes_{yyyyMMdd}.csv")
        self.cb_separator     = QComboBox(); self.cb_separator.setStyleSheet(self._combo_style())
        self.cb_encoding      = QComboBox(); self.cb_encoding.setStyleSheet(self._combo_style())
        self.inp_chunk_size   = QSpinBox()
        self.inp_chunk_size.setRange(1_000, 1_000_000); self.inp_chunk_size.setValue(50_000)
        self.inp_chunk_size.setSingleStep(10_000); self.inp_chunk_size.setStyleSheet(self._input_style())

        self._load_ftp_profiles()
        for label, val in self.SEPARATORS:
            self.cb_separator.addItem(label, val)
        for label, val in self.ENCODINGS:
            self.cb_encoding.addItem(label, val)
        self.cb_encoding.setCurrentIndex(1)   # utf-8-sig par défaut

        lbl_tokens = QLabel("{yyyy} {yy} {MM} {dd} {HH} {mm} {yyyyMMdd}")
        lbl_tokens.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-style: italic;")

        f3.addRow(self._label("Profil FTP *"),       self.cb_ftp)
        f3.addRow(self._label("Dossier distant *"),  self.inp_remote_path)
        f3.addRow(self._label("Nom de fichier *"),   self.inp_filename)
        f3.addRow("",                                lbl_tokens)
        f3.addRow(self._label("Séparateur CSV"),     self.cb_separator)
        f3.addRow(self._label("Encodage"),           self.cb_encoding)
        f3.addRow(self._label("Chunk (lignes)"),     self.inp_chunk_size)
        root.addLayout(f3)

        root.addWidget(self._sep())

        # ── Section 4 : planification ──
        root.addWidget(self._section_label("④ Planification"))
        f4 = QFormLayout(); f4.setSpacing(10)
        f4.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f4.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.cb_freq = QComboBox(); self.cb_freq.setStyleSheet(self._combo_style())
        for label, val in self.FREQ_LABELS:
            self.cb_freq.addItem(label, val)
        self.cb_freq.currentIndexChanged.connect(self._on_freq_changed)

        self.inp_time = self._input("HH:MM  ex : 06:00")
        self.inp_time.setText("06:00")
        self.inp_time.setFixedWidth(120)

        self.cb_day_week = QComboBox(); self.cb_day_week.setStyleSheet(self._combo_style())
        for i, d in enumerate(self.DAYS_WEEK):
            self.cb_day_week.addItem(d, i)

        self.inp_day_month = QSpinBox()
        self.inp_day_month.setRange(1, 28); self.inp_day_month.setValue(1)
        self.inp_day_month.setStyleSheet(self._input_style()); self.inp_day_month.setFixedWidth(80)

        self.inp_cron = self._input("ex : 0 6 * * 1-5  (min h j m jours)")

        f4.addRow(self._label("Fréquence"),   self.cb_freq)
        f4.addRow(self._label("Heure"),       self.inp_time)
        self._row_day_week  = (self._label("Jour (sem.)"), self.cb_day_week)
        self._row_day_month = (self._label("Jour (mois)"), self.inp_day_month)
        self._row_cron      = (self._label("Expression"),  self.inp_cron)
        f4.addRow(*self._row_day_week)
        f4.addRow(*self._row_day_month)
        f4.addRow(*self._row_cron)
        self._freq_form = f4
        root.addLayout(f4)
        self._on_freq_changed(0)   # masque les champs non pertinents

        root.addStretch()

        # ── Boutons (fixés en bas, hors du scroll) ──
        btn_sep = QFrame(); btn_sep.setFrameShape(QFrame.HLine)
        btn_sep.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        self._dialog_root.addWidget(btn_sep)

        btn_row = QHBoxLayout(); btn_row.setContentsMargins(28, 10, 28, 14); btn_row.setSpacing(10)
        btn_row.addStretch()
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(36); btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Enregistrer")
        btn_save.setFixedHeight(36); btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_save)
        self._dialog_root.addLayout(btn_row)

    # ── Logique ──────────────────────────────

    def _load_oracle_profiles(self):
        from database import db_manager as db
        self.cb_oracle.clear()
        self.cb_oracle.addItem("— sélectionner —", None)
        for p in db.get_oracle_profiles():
            self.cb_oracle.addItem(p.name, p.id)

    def _load_queries(self, oracle_id=None):
        from database import db_manager as db
        self.cb_query.clear()
        self.cb_query.addItem("— sélectionner —", None)
        for q in db.get_sql_queries():
            if oracle_id is None or q.oracle_profile_id == oracle_id:
                self.cb_query.addItem(q.name, q.id)

    def _load_ftp_profiles(self):
        from database import db_manager as db
        self.cb_ftp.clear()
        self.cb_ftp.addItem("— sélectionner —", None)
        for p in db.get_ftp_profiles():
            self.cb_ftp.addItem(p.name, p.id)

    def _on_oracle_changed(self, _):
        oracle_id = self.cb_oracle.currentData()
        self._load_queries(oracle_id)

    def _on_freq_changed(self, _):
        freq = self.cb_freq.currentData()
        self._row_day_week[0].setVisible(freq == "WEEKLY")
        self._row_day_week[1].setVisible(freq == "WEEKLY")
        self._row_day_month[0].setVisible(freq == "MONTHLY")
        self._row_day_month[1].setVisible(freq == "MONTHLY")
        self._row_cron[0].setVisible(freq == "CUSTOM")
        self._row_cron[1].setVisible(freq == "CUSTOM")
        self.inp_time.setEnabled(freq != "CUSTOM")

    def _on_save(self):
        if not self._validate():
            return
        from database import db_manager as db

        name        = self.inp_name.text().strip()
        desc        = self.inp_desc.text().strip() or None
        oracle_id   = self.cb_oracle.currentData()
        query_id    = self.cb_query.currentData()
        ftp_id      = self.cb_ftp.currentData()
        remote_path = self.inp_remote_path.text().strip()
        filename    = self.inp_filename.text().strip()
        separator   = self.cb_separator.currentData()
        encoding    = self.cb_encoding.currentData()
        chunk_size  = self.inp_chunk_size.value()
        freq        = self.cb_freq.currentData()
        sched_time  = self.inp_time.text().strip()
        sched_day   = None
        cron_expr   = None

        if freq == "WEEKLY":
            sched_day = self.cb_day_week.currentData()
        elif freq == "MONTHLY":
            sched_day = self.inp_day_month.value()
        elif freq == "CUSTOM":
            cron_expr = self.inp_cron.text().strip()

        if self._pipeline:
            with db.get_session() as s:
                from database.models import Pipeline
                p = s.get(Pipeline, self._pipeline.id)
                p.name              = name
                p.description       = desc
                p.oracle_profile_id = oracle_id
                p.sql_query_id      = query_id
                p.ftp_profile_id    = ftp_id
                p.remote_path_tpl   = remote_path
                p.filename_tpl      = filename
                p.csv_separator     = separator
                p.csv_encoding      = encoding
                p.csv_chunk_size    = chunk_size
                p.frequency         = freq
                p.scheduled_time    = sched_time
                p.scheduled_day     = sched_day
                p.cron_expression   = cron_expr
        else:
            db.create_pipeline(
                name=name, description=desc,
                oracle_profile_id=oracle_id, sql_query_id=query_id,
                ftp_profile_id=ftp_id,
                remote_path_tpl=remote_path, filename_tpl=filename,
                csv_separator=separator, csv_encoding=encoding,
                csv_chunk_size=chunk_size,
                frequency=freq, scheduled_time=sched_time,
                scheduled_day=sched_day, cron_expression=cron_expr,
            )
        self.accept()

    def _validate(self) -> bool:
        if not self.inp_name.text().strip():
            self.inp_name.setStyleSheet(self._input_style(error=True)); self.inp_name.setFocus(); return False
        if not self.cb_oracle.currentData():
            self.cb_oracle.setFocus(); return False
        if not self.cb_query.currentData():
            self.cb_query.setFocus(); return False
        if not self.cb_ftp.currentData():
            self.cb_ftp.setFocus(); return False
        if not self.inp_remote_path.text().strip():
            self.inp_remote_path.setStyleSheet(self._input_style(error=True))
            self.inp_remote_path.setFocus(); return False
        if not self.inp_filename.text().strip():
            self.inp_filename.setStyleSheet(self._input_style(error=True))
            self.inp_filename.setFocus(); return False
        return True

    def _fill_fields(self, p):
        self.inp_name.setText(p.name)
        self.inp_desc.setText(p.description or "")
        _set_combo(self.cb_oracle, p.oracle_profile_id)
        self._load_queries(p.oracle_profile_id)
        _set_combo(self.cb_query, p.sql_query_id)
        _set_combo(self.cb_ftp, p.ftp_profile_id)
        self.inp_remote_path.setText(p.remote_path_tpl or "")
        self.inp_filename.setText(p.filename_tpl or "")
        _set_combo_data(self.cb_separator, p.csv_separator)
        _set_combo_data(self.cb_encoding, p.csv_encoding)
        self.inp_chunk_size.setValue(p.csv_chunk_size or 50_000)
        freq = _status_str(p.frequency) if p.frequency else "DAILY"
        _set_combo_data(self.cb_freq, freq)
        self.inp_time.setText(p.scheduled_time or "06:00")
        if p.scheduled_day is not None:
            if freq == "WEEKLY":
                self.cb_day_week.setCurrentIndex(p.scheduled_day)
            elif freq == "MONTHLY":
                self.inp_day_month.setValue(p.scheduled_day)
        if p.cron_expression:
            self.inp_cron.setText(p.cron_expression)

    # ── Helpers visuels ──────────────────────

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 12px; font-weight: 700; "
            f"letter-spacing: 0.5px; padding-top: 4px;"
        )
        return lbl

    def _input(self, placeholder="") -> QLineEdit:
        w = QLineEdit(); w.setPlaceholderText(placeholder); w.setFixedHeight(34)
        w.setStyleSheet(self._input_style())
        return w

    def _input_style(self, error=False) -> str:
        border = COLORS["danger"] if error else COLORS["border"]
        return (f"QLineEdit, QSpinBox {{ background: {COLORS['bg_card']}; "
                f"border: 1px solid {border}; border-radius: 4px; "
                f"padding: 6px 10px; color: {COLORS['text_main']}; font-size: 13px; }}"
                f"QLineEdit:focus, QSpinBox:focus {{ border-color: {COLORS['accent']}; }}")

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


def _set_combo(cb: QComboBox, value) -> None:
    for i in range(cb.count()):
        if cb.itemData(i) == value:
            cb.setCurrentIndex(i); return


def _set_combo_data(cb: QComboBox, value: str) -> None:
    for i in range(cb.count()):
        if cb.itemData(i) == value:
            cb.setCurrentIndex(i); return


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