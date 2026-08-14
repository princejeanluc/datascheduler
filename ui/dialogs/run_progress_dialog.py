"""
DataScheduler — ui/dialogs/run_progress_dialog.py
Dialogue de suivi d'exécution d'un pipeline en temps réel.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QPlainTextEdit, QProgressBar,
)
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QFont
from ui.styles import COLORS, DIALOG_STYLE, FONT_MONO


# ──────────────────────────────────────────────
#  THREAD + DIALOGUE D'EXÉCUTION EN TEMPS RÉEL
# ──────────────────────────────────────────────

class RunProgressThread(QThread):
    """Lance run_pipeline() dans un thread et émet les signaux vers l'UI."""
    progress_signal = Signal(str, int)   # step, pct
    finished_signal = Signal(object)     # PipelineResult

    def __init__(self, pipeline_id: int, resume_from_run_id: int | None = None):
        super().__init__()
        self.pipeline_id = pipeline_id
        self.resume_from_run_id = resume_from_run_id

    def run(self):
        from core.pipeline import run_pipeline
        result = run_pipeline(
            self.pipeline_id,
            on_progress=lambda step, pct: self.progress_signal.emit(step, pct),
            resume_from_run_id=self.resume_from_run_id,
        )
        self.finished_signal.emit(result)


class RunProgressDialog(QDialog):
    """
    Dialogue modal d'exécution d'un pipeline.
    Affiche la progression pas à pas, les logs, et le résultat final.
    Ne peut pas être fermé pendant l'exécution.
    """

    def __init__(self, pipeline_id: int, pipeline_name: str, parent=None,
                 resume_from_run_id: int | None = None):
        super().__init__(parent)
        self._thread = None
        self._pipeline_id = pipeline_id
        self._pipeline_name = pipeline_name
        self._resume_from_run_id = resume_from_run_id
        title = f"Reprise — {pipeline_name}" if resume_from_run_id else f"Exécution — {pipeline_name}"
        self.setWindowTitle(title)
        self.setMinimumSize(500, 340)
        self.setModal(True)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui(pipeline_name)
        self._start(pipeline_id, resume_from_run_id)

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
        self.log_area.setFont(QFont(FONT_MONO, 10))
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
        self.btn_resume = QPushButton("Reprendre depuis l'échec")
        self.btn_resume.setObjectName("secondary")
        self.btn_resume.setFixedHeight(34)
        self.btn_resume.setVisible(False)
        self.btn_resume.clicked.connect(self._on_resume_clicked)
        btn_row.addWidget(self.btn_resume)
        self.btn_close = QPushButton("Fermer")
        self.btn_close.setFixedHeight(34)
        self.btn_close.setEnabled(False)
        self.btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_close)
        root.addLayout(btn_row)

    def _start(self, pipeline_id: int, resume_from_run_id: int | None = None):
        self._thread = RunProgressThread(pipeline_id, resume_from_run_id)
        self._thread.progress_signal.connect(self._on_progress)
        self._thread.finished_signal.connect(self._on_finished)
        self._thread.start()

    def _on_progress(self, step: str, pct: int):
        self.lbl_step.setText(step)
        self.progress_bar.setValue(pct)
        self.log_area.appendPlainText(f"  {step}")

    def _on_finished(self, result):
        self.btn_close.setEnabled(True)
        self._last_result = result
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
            self._offer_resume_if_available(result)

        self.lbl_result.setText(txt)
        self.lbl_result.setStyleSheet(
            f"color: {color}; font-size: 13px; font-weight: 600;"
        )
        self.lbl_result.setVisible(True)

    def _offer_resume_if_available(self, result):
        if not result.run_id:
            return
        from database import db_manager as db
        resumable = db.get_last_resumable_run(self._pipeline_id)
        if resumable and resumable.id == result.run_id:
            self.btn_resume.setVisible(True)

    def _on_resume_clicked(self):
        run_id = self._last_result.run_id
        self.accept()
        RunProgressDialog(
            self._pipeline_id, self._pipeline_name, self.parent(),
            resume_from_run_id=run_id,
        ).exec()

    def closeEvent(self, event):
        if self._thread and self._thread.isRunning():
            event.ignore()   # bloque la fermeture pendant l'exécution
        else:
            super().closeEvent(event)
