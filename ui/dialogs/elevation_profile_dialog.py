"""
DataScheduler — ui/dialogs/elevation_profile_dialog.py
Dialogue de création / édition d'un profil d'élévation (sudo su <utilisateur cible> — compte
technique généralement partagé par l'équipe, ex : "nifi") — étape SQOOP_EXPORT, alternative à
Kerberos pour les équipes qui ne l'utilisent pas. Comme Kerberos, ce test n'est pas autonome : il
faut réellement tenter le sudo su depuis une machine, donc le test exige de choisir un profil SSH
existant (nœud edge) pour le mener.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QFrame,
)
from PySide6.QtCore import Qt, QThread, Signal
from ui.styles import COLORS, DIALOG_STYLE


# ──────────────────────────────────────────────
#  THREAD TEST CONNEXION (non-bloquant)
# ──────────────────────────────────────────────

class ElevationTestThread(QThread):
    result_ready = Signal(bool, str)   # success, message

    def __init__(self, ssh_config, elevation_config):
        super().__init__()
        self.ssh_config = ssh_config
        self.elevation_config = elevation_config

    def run(self):
        from core.hadoop_edge import test_elevation_auth
        r = test_elevation_auth(self.ssh_config, self.elevation_config)
        self.result_ready.emit(r.success, r.message)


# ──────────────────────────────────────────────
#  DIALOGUE
# ──────────────────────────────────────────────

class ElevationProfileDialog(QDialog):
    """Création / édition d'un profil d'élévation (utilisateur cible + mot de passe, souvent
    partagé par toute l'équipe — pas nominatif comme Kerberos)."""

    def __init__(self, parent=None, profile=None):
        super().__init__(parent)
        self._profile     = profile
        self._test_thread = None
        self.setWindowTitle("Profil d'élévation (sudo)" if profile is None else "Modifier le profil d'élévation")
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

        title = QLabel("Élévation de privilèges (sudo su)")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title)
        note = QLabel(
            "Compte technique généralement partagé par l'équipe (ex : « nifi ») — le mot de "
            "passe est chiffré au repos. Utilisé par l'étape Export Sqoop pour basculer vers cet "
            "utilisateur après connexion SSH, avant d'exécuter sqoop."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-style: italic;")
        root.addWidget(note)
        root.addWidget(self._sep())

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.inp_name = self._input("ex : ELEVATION_NIFI")
        self.inp_target_user = self._input("ex : nifi")
        self.inp_pass = self._input("••••••••", password=True)

        form.addRow(self._label("Nom du profil *"),       self.inp_name)
        form.addRow(self._label("Utilisateur cible *"),   self.inp_target_user)
        form.addRow(self._label("Mot de passe *"),        self.inp_pass)
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
        from database import db_manager as db
        frame = QFrame(); frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 10); layout.setSpacing(8)

        row1 = QHBoxLayout(); row1.setSpacing(8)
        row1.addWidget(self._label("Profil SSH pour le test"))
        self.cb_ssh_profile = QComboBox()
        self.cb_ssh_profile.setStyleSheet(self._combo_style())
        self.cb_ssh_profile.addItem("— Sélectionner un profil SSH —", None)
        for p in db.get_ssh_profiles():
            self.cb_ssh_profile.addItem(p.name, p.id)
        row1.addWidget(self.cb_ssh_profile, stretch=1)
        layout.addLayout(row1)
        hint = QLabel(
            "Une élévation ne peut pas se tester seule — sudo su doit tourner depuis une "
            "machine ; le test le tente sur le profil SSH choisi ci-dessus."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; font-style: italic;")
        layout.addWidget(hint)

        row2 = QHBoxLayout(); row2.setSpacing(12)
        self.btn_test = QPushButton("⚡  Tester (sudo su)")
        self.btn_test.setObjectName("secondary"); self.btn_test.setFixedHeight(32)
        self.btn_test.clicked.connect(self._on_test)
        self.lbl_test_result = QLabel("—")
        self.lbl_test_result.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
        row2.addWidget(self.btn_test); row2.addWidget(self.lbl_test_result, stretch=1)
        layout.addLayout(row2)
        return frame

    # ── Logique ──────────────────────────────

    def _on_test(self):
        from database import db_manager as db
        from core.hadoop_edge import config_from_profile

        ssh_id = self.cb_ssh_profile.currentData()
        if not ssh_id:
            self.lbl_test_result.setText("⚠  Choisir un profil SSH pour le test")
            self.lbl_test_result.setStyleSheet(f"color: {COLORS['warning']}; font-size: 12px;")
            return
        ssh_profile = db.get_ssh_profile(ssh_id)
        if not ssh_profile:
            self.lbl_test_result.setText("⚠  Profil SSH introuvable")
            self.lbl_test_result.setStyleSheet(f"color: {COLORS['warning']}; font-size: 12px;")
            return

        elevation_config = self._build_config()
        if elevation_config is None:
            return

        self.btn_test.setEnabled(False)
        self.lbl_test_result.setText("sudo su en cours…")
        self.lbl_test_result.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
        self._test_thread = ElevationTestThread(config_from_profile(ssh_profile), elevation_config)
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
            db.record_profile_test_result("elevation", self._profile.id, success)

    def _on_save(self):
        if not self._validate():
            return
        from database import db_manager as db
        name        = self.inp_name.text().strip()
        target_user = self.inp_target_user.text().strip()
        pwd         = self.inp_pass.text().strip()

        if self._profile:
            db.update_elevation_profile(self._profile.id, name=name, target_user=target_user,
                                        password=pwd or None)
        else:
            db.create_elevation_profile(name=name, target_user=target_user, password=pwd)
        self.accept()

    def _validate(self) -> bool:
        required = [(self.inp_name, "Nom"), (self.inp_target_user, "Utilisateur cible")]
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
        from core.hadoop_edge import ElevationConfig
        from database import crypto
        target_user = self.inp_target_user.text().strip()
        pwd         = self.inp_pass.text().strip()
        if not pwd and self._profile:
            pwd = crypto.decrypt(self._profile.password)
        if not target_user or not pwd:
            self.lbl_test_result.setText("⚠  Remplir Utilisateur cible / Mot de passe")
            self.lbl_test_result.setStyleSheet(f"color: {COLORS['warning']}; font-size: 12px;")
            return None
        return ElevationConfig(target_user=target_user, password=pwd)

    def _fill_fields(self, profile):
        self.inp_name.setText(profile.name)
        self.inp_target_user.setText(profile.target_user)
        self.inp_pass.setPlaceholderText("•••••••• (laisser vide pour conserver)")

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
            QLineEdit {{
                background: {COLORS['bg_card']}; border: 1px solid {border};
                border-radius: 4px; padding: 6px 10px;
                color: {COLORS['text_main']}; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {COLORS['accent']}; }}
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
