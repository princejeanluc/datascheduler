"""
DataScheduler — ui/dialogs/connection_health_dialog.py
Bilan de santé des connexions (chantier UX fiabilité, D.2) : dernier statut de test connu pour
chaque profil (Oracle/base de données/FTP/SMTP), avec un bouton pour tout retester d'un coup.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QAbstractItemView,
)
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QColor
from ui.styles import COLORS, DIALOG_STYLE
from ui.main_window.widgets import _configure_columns

_CATEGORY_LABELS = {
    "oracle":   "Oracle",
    "database": "Base de données",
    "ftp":      "FTP",
    "smtp":     "SMTP",
    "ssh":      "SSH",
    "kerberos": "Kerberos",
}


def _collect_profiles() -> list[dict]:
    from database import db_manager as db
    rows = []
    for p in db.get_oracle_profiles():
        rows.append({
            "category": "oracle", "db_type": "ORACLE", "id": p.id, "name": p.name,
            "last_tested_at": p.last_tested_at, "last_test_success": p.last_test_success,
        })
    for p in db.get_database_profiles():
        dtype = p.db_type.value if hasattr(p.db_type, "value") else str(p.db_type)
        rows.append({
            "category": "database", "db_type": dtype, "id": p.id, "name": p.name,
            "last_tested_at": p.last_tested_at, "last_test_success": p.last_test_success,
        })
    for p in db.get_ftp_profiles():
        rows.append({
            "category": "ftp", "db_type": None, "id": p.id, "name": p.name,
            "last_tested_at": p.last_tested_at, "last_test_success": p.last_test_success,
        })
    for p in db.get_smtp_profiles():
        rows.append({
            "category": "smtp", "db_type": None, "id": p.id, "name": p.name,
            "last_tested_at": p.last_tested_at, "last_test_success": p.last_test_success,
        })
    for p in db.get_ssh_profiles():
        rows.append({
            "category": "ssh", "db_type": None, "id": p.id, "name": p.name,
            "last_tested_at": p.last_tested_at, "last_test_success": p.last_test_success,
        })
    for p in db.get_kerberos_profiles():
        rows.append({
            "category": "kerberos", "db_type": None, "id": p.id, "name": p.name,
            "last_tested_at": p.last_tested_at, "last_test_success": p.last_test_success,
        })
    return rows


def _test_one(category: str, profile_id: int, db_type):
    """
    Teste une connexion réelle — mêmes connecteurs/config_from_profile que les dialogues
    de profil et core/pipeline.py::_test_reference_connection (même principe, couche différente).
    Ne lève jamais (les test_connection() sous-jacents non plus).

    Retourne (success, message) — sauf pour "kerberos", où success vaut None : un ticket
    Kerberos ne se teste pas seul (il faut une machine sur laquelle lancer kinit), donc le
    bilan groupé ne peut pas le tester automatiquement. None (pas False) signale à
    _HealthCheckThread de ne PAS enregistrer ce non-test comme un échec réel — le test manuel
    reste disponible depuis le dialogue du profil Kerberos lui-même.
    """
    from database import db_manager as db
    try:
        if category in ("oracle", "database"):
            from core.sql_db import SqlConnector, get_profile_object, config_from_profile
            profile = get_profile_object(db_type, profile_id)
            if not profile:
                return False, "Profil introuvable."
            result = SqlConnector(config_from_profile(db_type, profile)).test_connection()
        elif category == "ftp":
            from core.ftp import FtpUploader, config_from_profile
            profile = db.get_ftp_profile(profile_id)
            if not profile:
                return False, "Profil introuvable."
            result = FtpUploader(config_from_profile(profile)).test_connection()
        elif category == "smtp":
            from core.email import EmailSender, config_from_profile
            profile = db.get_smtp_profile(profile_id)
            if not profile:
                return False, "Profil introuvable."
            result = EmailSender(config_from_profile(profile)).test_connection()
        elif category == "ssh":
            from core.spark import test_ssh_connection, config_from_profile
            profile = db.get_ssh_profile(profile_id)
            if not profile:
                return False, "Profil introuvable."
            result = test_ssh_connection(config_from_profile(profile))
        elif category == "kerberos":
            return None, "Test uniquement disponible depuis le profil Kerberos — nécessite de choisir un profil SSH."
        else:
            return False, "Catégorie inconnue."
        return result.success, result.message
    except Exception as e:
        return False, str(e)


# ──────────────────────────────────────────────
#  THREAD (teste plusieurs profils en séquence — ne doit pas geler l'UI)
# ──────────────────────────────────────────────

class _HealthCheckThread(QThread):
    # index de ligne, succès (object, pas bool : doit pouvoir transporter None sans coercition —
    # "kerberos" n'est pas testable en bulk, voir _test_one), message
    row_tested = Signal(int, object, str)

    def __init__(self, rows: list[dict]):
        super().__init__()
        self._rows = rows

    def run(self):
        from database import db_manager as db
        for i, row in enumerate(self._rows):
            success, message = _test_one(row["category"], row["id"], row["db_type"])
            if success is not None:
                db.record_profile_test_result(row["category"], row["id"], success)
            self.row_tested.emit(i, success, message)


# ──────────────────────────────────────────────
#  DIALOGUE
# ──────────────────────────────────────────────

class ConnectionHealthDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._rows: list[dict] = []
        self.setWindowTitle("Bilan de santé des connexions")
        self.setMinimumSize(620, 460)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()
        self._load_rows()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Bilan de santé des connexions")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        header.addWidget(title); header.addStretch()
        self.btn_test_all = QPushButton("Tester tout")
        self.btn_test_all.setFixedHeight(32)
        self.btn_test_all.clicked.connect(self._on_test_all)
        header.addWidget(self.btn_test_all)
        root.addLayout(header)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        root.addWidget(sep)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Catégorie", "Nom", "Dernier test", "Statut"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        _configure_columns(self.table, stretch_cols={1})
        root.addWidget(self.table, stretch=1)

        btn_row = QHBoxLayout(); btn_row.addStretch()
        btn_close = QPushButton("Fermer")
        btn_close.setObjectName("secondary")
        btn_close.setFixedHeight(34)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

    def _load_rows(self):
        self._rows = _collect_profiles()
        self.table.setRowCount(len(self._rows))
        for i, row in enumerate(self._rows):
            self._render_row(i, row["last_tested_at"], row["last_test_success"])

    def _render_row(self, row_idx: int, last_tested_at, last_test_success, message: str = None):
        row = self._rows[row_idx]
        cells = [
            _CATEGORY_LABELS.get(row["category"], row["category"]),
            row["name"],
            last_tested_at.strftime("%d/%m/%Y %H:%M") if last_tested_at else "Jamais testé",
        ]
        for c_idx, cell in enumerate(cells):
            item = QTableWidgetItem(cell)
            item.setForeground(QColor(COLORS["text_main"]))
            self.table.setItem(row_idx, c_idx, item)

        if last_test_success is None:
            status_text, color = "—", COLORS["text_dim"]
        elif last_test_success:
            status_text, color = "✅ OK", COLORS["success"]
        else:
            status_text, color = "❌ Échec", COLORS["danger"]
        status_item = QTableWidgetItem(status_text)
        status_item.setForeground(QColor(color))
        if message:
            status_item.setToolTip(message)
        self.table.setItem(row_idx, 3, status_item)
        self.table.setRowHeight(row_idx, 36)

    def _on_test_all(self):
        if not self._rows:
            return
        self.btn_test_all.setEnabled(False)
        self._thread = _HealthCheckThread(self._rows)
        self._thread.row_tested.connect(self._on_row_tested)
        self._thread.finished.connect(lambda: self.btn_test_all.setEnabled(True))
        self._thread.start()

    def _on_row_tested(self, row_idx: int, success, message: str):
        from datetime import datetime
        if success is None:
            # "kerberos" : non testable en bulk (voir _test_one) — laisse le statut persisté
            # inchangé (probablement "Jamais testé"), affiche juste le message explicatif.
            row = self._rows[row_idx]
            self._render_row(row_idx, row["last_tested_at"], row["last_test_success"], message)
        else:
            self._render_row(row_idx, datetime.utcnow(), success, message)

    def closeEvent(self, event):
        if self._thread and self._thread.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)
