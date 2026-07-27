"""
DataScheduler — ui/dialogs/oracle_dialog.py
Dialogue de création / édition d'un profil Oracle.
"""

from PySide6.QtWidgets import (
    QComboBox, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QSpinBox, QRadioButton, QButtonGroup, QPushButton, QFrame,
    QWidget,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
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
