"""
DataScheduler — ui/main_window/run_log_dialog.py
Dialogue "Voir le log complet" d'une exécution — extrait de HistoryView._open_log() pour être
réutilisé aussi par la vue détail par pipeline (chantier UX fiabilité, D.1), sans dupliquer la
construction du dialogue.
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QLabel, QPushButton
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from ui.styles import COLORS, DIALOG_STYLE
from .widgets import _status_str, FONT_MONO


def open_run_log_dialog(parent, run_id: int) -> None:
    from database import db_manager as db
    from database.models import PipelineRun

    with db.get_session() as s:
        run = s.get(PipelineRun, run_id)
        if not run:
            return
        pname    = run.pipeline.name if run.pipeline else str(run.pipeline_id)
        st       = _status_str(run.status)
        log_text = run.log_text or "(aucun log enregistré)"
        err_text = run.error_message or ""

    dlg = QDialog(parent)
    dlg.setWindowTitle(f"Log — {pname}")
    dlg.setMinimumSize(640, 420)
    dlg.setStyleSheet(DIALOG_STYLE)

    vl = QVBoxLayout(dlg)
    vl.setContentsMargins(20, 16, 20, 16)
    vl.setSpacing(12)

    lbl_title = QLabel(f"{pname}  ·  {st}")
    lbl_title.setStyleSheet(
        f"font-size: 15px; font-weight: 700; color: "
        f"{COLORS['success'] if st == 'SUCCESS' else COLORS['danger'] if st == 'FAILED' else COLORS['accent']};"
    )
    vl.addWidget(lbl_title)

    if err_text:
        lbl_err = QLabel(f"Erreur : {err_text}")
        lbl_err.setStyleSheet(f"color: {COLORS['danger']}; font-size: 12px;")
        lbl_err.setWordWrap(True)
        vl.addWidget(lbl_err)

    txt = QTextEdit()
    txt.setReadOnly(True)
    txt.setFont(QFont(FONT_MONO, 11))
    txt.setStyleSheet(
        f"background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
        f"border: 1px solid {COLORS['border']}; border-radius: 4px;"
    )
    txt.setPlainText(log_text)
    vl.addWidget(txt)

    btn_close = QPushButton("Fermer")
    btn_close.setFixedHeight(34)
    btn_close.clicked.connect(dlg.accept)
    vl.addWidget(btn_close, alignment=Qt.AlignRight)

    dlg.exec()
