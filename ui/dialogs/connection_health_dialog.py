"""
DataScheduler — ui/dialogs/connection_health_dialog.py
Bilan de santé des connexions (chantier UX fiabilité, D.2) : dernier statut de test connu pour
chaque profil (Oracle/base de données/FTP/SMTP), avec un bouton pour tout retester d'un coup.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont
from ui.styles import COLORS, DIALOG_STYLE, FONT_MONO
from ui.time_display import fmt_relative
from ui.main_window.widgets import _configure_columns, _type_icon_badge, _status_dot_row

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

        # A10 : surtitre + titre + sous-titre (même patron que les autres en-têtes de dialogue
        # restylés) — remplace l'unique QLabel "Bilan de santé des connexions" d'avant ce lot.
        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        eyebrow = QLabel("BILAN DE SANTÉ")
        eyebrow.setStyleSheet(
            f"font-family: {FONT_MONO}; font-size: 10px; letter-spacing: 0.06em; "
            f"color: {COLORS['text_dim']};"
        )
        title_col.addWidget(eyebrow)
        title = QLabel("Test de toutes les connexions")
        title.setStyleSheet(f"font-size: 17px; font-weight: 600; color: {COLORS['text_main']};")
        title_col.addWidget(title)
        subtitle = QLabel("Les connexions sont testées une par une, sans rien écrire ni lancer.")
        subtitle.setStyleSheet(f"font-size: 12px; color: {COLORS['text_dim']};")
        title_col.addWidget(subtitle)

        header = QHBoxLayout()
        header.addLayout(title_col); header.addStretch()
        self.btn_test_all = QPushButton("Tester tout")
        self.btn_test_all.setFixedHeight(32)
        self.btn_test_all.clicked.connect(self._on_test_all)
        header.addWidget(self.btn_test_all, alignment=Qt.AlignTop)
        root.addLayout(header)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        root.addWidget(sep)

        # A10 : icône de type (remplace la colonne "Catégorie" en texte) / Nom / Statut (point +
        # mot, même vocabulaire que A5 — jamais _health_badge/émoji) / Message en clair (plus
        # seulement en infobulle) / heure relative (plus `fmt_datetime` absolu).
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "Nom", "Statut", "Message", "Dernier test"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        _configure_columns(self.table, stretch_cols={3})
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 36)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(2, 90)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 110)
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
        self.table.setCellWidget(row_idx, 0, _type_icon_badge(row["category"], size=26))

        name_item = QTableWidgetItem(row["name"])
        name_item.setForeground(QColor(COLORS["text_main"]))
        self.table.setItem(row_idx, 1, name_item)

        if row["category"] == "kerberos":
            # Jamais testable en masse (voir _test_one) — même texte que la maquette, quel que
            # soit le dernier résultat persisté (toujours None pour ce type en pratique).
            status_text, color, dashed = "non testable ici", COLORS["text_dim"], False
        elif last_test_success is True:
            status_text, color, dashed = "OK", COLORS["success"], False
        elif last_test_success is False:
            status_text, color, dashed = "Échec", COLORS["danger"], False
        else:
            status_text, color, dashed = "Jamais testé", COLORS["text_dim"], True
        self.table.setCellWidget(row_idx, 2, _status_dot_row(status_text, color, dashed=dashed))

        message_item = QTableWidgetItem(message or "")
        message_item.setForeground(QColor(COLORS["text_dim"]))
        message_item.setFont(QFont(FONT_MONO, 10))
        self.table.setItem(row_idx, 3, message_item)

        time_item = QTableWidgetItem(fmt_relative(last_tested_at) if last_tested_at else "—")
        time_item.setForeground(QColor(COLORS["text_dim"]))
        time_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row_idx, 4, time_item)

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
