"""
DataScheduler — ui/dialogs/database_profile_dialog.py
Dialogues de profil de base de données générique (MySQL/PostgreSQL/SQL Server).
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QSpinBox, QPushButton, QFrame, QCheckBox,
)
from PySide6.QtCore import Qt, QThread, Signal
from ui.styles import COLORS, DIALOG_STYLE


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

        if self._profile:
            from database import db_manager as db
            db.record_profile_test_result("database", self._profile.id, success)

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
