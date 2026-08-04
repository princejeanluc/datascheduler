"""
DataScheduler — ui/dialogs/pipeline_dry_run_dialog.py
Dialogue de validation à blanc d'un pipeline (chantier UX autonomie, C.2) — vérifie sa forme,
que les profils/requêtes référencés existent encore, et que les connexions réelles fonctionnent,
sans rien exécuter.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QListWidget, QListWidgetItem,
)
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QColor
from ui.styles import COLORS, DIALOG_STYLE


# ──────────────────────────────────────────────
#  THREAD (peut enchaîner plusieurs tests réseau — ne doit pas geler l'UI)
# ──────────────────────────────────────────────

class _DryRunThread(QThread):
    result_ready = Signal(object)   # DryRunResult

    def __init__(self, pipeline_id: int):
        super().__init__()
        self.pipeline_id = pipeline_id

    def run(self):
        from core.pipeline import dry_run_pipeline
        self.result_ready.emit(dry_run_pipeline(self.pipeline_id))


# ──────────────────────────────────────────────
#  DIALOGUE
# ──────────────────────────────────────────────

class PipelineDryRunDialog(QDialog):
    """Dialogue modal de validation à blanc — ne peut pas se fermer pendant la vérification."""

    def __init__(self, pipeline_id: int, pipeline_name: str, parent=None):
        super().__init__(parent)
        self._thread = None
        self.setWindowTitle(f"Validation — {pipeline_name}")
        self.setMinimumSize(520, 380)
        self.setModal(True)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui(pipeline_name)
        self._start(pipeline_id)

    def _build_ui(self, pipeline_name: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        title = QLabel(f"Validation — {pipeline_name}")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        root.addWidget(sep)

        self.lbl_status = QLabel("Validation en cours…")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
        root.addWidget(self.lbl_status)

        self.list_findings = QListWidget()
        self.list_findings.setStyleSheet(
            f"QListWidget {{ background: {COLORS['bg_main']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 4px; }} QListWidget::item {{ padding: 6px 8px; }}"
        )
        root.addWidget(self.list_findings, stretch=1)

        btn_row = QHBoxLayout(); btn_row.addStretch()
        self.btn_close = QPushButton("Fermer")
        self.btn_close.setFixedHeight(34)
        self.btn_close.setEnabled(False)
        self.btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_close)
        root.addLayout(btn_row)

    def _start(self, pipeline_id: int):
        self._thread = _DryRunThread(pipeline_id)
        self._thread.result_ready.connect(self._on_result)
        self._thread.start()

    def _on_result(self, result):
        self.btn_close.setEnabled(True)
        self.list_findings.clear()

        if result.success and not result.errors and not result.warnings:
            self.lbl_status.setText(
                f"✅  Aucun problème détecté "
                f"({result.checked_connections} connexion(s) vérifiée(s))."
            )
            self.lbl_status.setStyleSheet(
                f"color: {COLORS['success']}; font-size: 13px; font-weight: 600;"
            )
            return

        if result.errors:
            self.lbl_status.setText(
                "❌  Validation échouée — corrigez les erreurs avant d'activer la planification."
            )
            color = COLORS["danger"]
        else:
            self.lbl_status.setText(
                f"⚠  Validé avec {len(result.warnings)} avertissement(s) "
                f"({result.checked_connections} connexion(s) vérifiée(s))."
            )
            color = COLORS["warning"]
        self.lbl_status.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 600;")

        for msg in result.errors:
            item = QListWidgetItem(f"❌  {msg}")
            item.setForeground(QColor(COLORS["danger"]))
            self.list_findings.addItem(item)
        for msg in result.warnings:
            item = QListWidgetItem(f"⚠  {msg}")
            item.setForeground(QColor(COLORS["warning"]))
            self.list_findings.addItem(item)

    def closeEvent(self, event):
        if self._thread and self._thread.isRunning():
            event.ignore()   # bloque la fermeture pendant la validation
        else:
            super().closeEvent(event)
