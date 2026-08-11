"""
DataScheduler — ui/main_window/run_log_dialog.py
Dialogue "Voir le log complet" d'une exécution — extrait de HistoryView._open_log() pour être
réutilisé aussi par la vue détail par pipeline (chantier UX fiabilité, D.1), sans dupliquer la
construction du dialogue.
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QLabel, QPushButton
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from ui.styles import COLORS, DIALOG_STYLE
from .widgets import _status_str, FONT_MONO

_LIVE_REFRESH_INTERVAL_MS = 2000


def open_run_log_dialog(parent, run_id: int) -> None:
    """
    Si le run est encore RUNNING à l'ouverture, le log/l'étape courante sont relus depuis la
    base à intervalle régulier (chantier N — PipelineRun.log_text/current_step_label sont
    désormais écrits en continu par run_pipeline(), plus seulement à la fin) — le
    rafraîchissement s'arrête de lui-même dès que le run atteint un statut terminal.
    """
    from database import db_manager as db
    from database.models import PipelineRun

    with db.get_session() as s:
        run = s.get(PipelineRun, run_id)
        if not run:
            return
        pipeline_id     = run.pipeline_id
        pname           = run.pipeline.name if run.pipeline else str(run.pipeline_id)
        st              = _status_str(run.status)
        log_text        = run.log_text or "(aucun log enregistré)"
        err_text        = run.error_message or ""
        current_step    = run.current_step_label or ""
        is_resumable    = bool(run.resumable_state_json)

    dlg = QDialog(parent)
    dlg.setWindowTitle(f"Log — {pname}")
    dlg.setMinimumSize(640, 420)
    dlg.setStyleSheet(DIALOG_STYLE)

    vl = QVBoxLayout(dlg)
    vl.setContentsMargins(20, 16, 20, 16)
    vl.setSpacing(12)

    def _title_color(status: str) -> str:
        if status == "SUCCESS":
            return COLORS["success"]
        if status == "FAILED":
            return COLORS["danger"]
        return COLORS["accent"]

    lbl_title = QLabel(f"{pname}  ·  {st}")
    lbl_title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {_title_color(st)};")
    vl.addWidget(lbl_title)

    lbl_step = QLabel(f"Étape en cours : {current_step}" if current_step else "")
    lbl_step.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
    lbl_step.setVisible(bool(current_step))
    vl.addWidget(lbl_step)

    lbl_err = QLabel(f"Erreur : {err_text}" if err_text else "")
    lbl_err.setStyleSheet(f"color: {COLORS['danger']}; font-size: 12px;")
    lbl_err.setWordWrap(True)
    lbl_err.setVisible(bool(err_text))
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

    if st == "RUNNING":
        state = {"status": st}

        def _refresh_live():
            with db.get_session() as s:
                run = s.get(PipelineRun, run_id)
                if not run:
                    timer.stop()
                    return
                new_log = run.log_text or "(aucun log enregistré)"
                if new_log != txt.toPlainText():
                    bar = txt.verticalScrollBar()
                    at_bottom = bar.value() >= bar.maximum() - 4
                    txt.setPlainText(new_log)
                    if at_bottom:
                        bar.setValue(bar.maximum())
                step_label = run.current_step_label or ""
                lbl_step.setText(f"Étape en cours : {step_label}" if step_label else "")
                lbl_step.setVisible(bool(step_label))
                new_status = _status_str(run.status)
                if new_status != state["status"]:
                    state["status"] = new_status
                    lbl_title.setText(f"{pname}  ·  {new_status}")
                    lbl_title.setStyleSheet(
                        f"font-size: 15px; font-weight: 700; color: {_title_color(new_status)};"
                    )
                    if run.error_message:
                        lbl_err.setText(f"Erreur : {run.error_message}")
                        lbl_err.setVisible(True)
                    if new_status != "RUNNING":
                        lbl_step.setVisible(False)
                        timer.stop()

        timer = QTimer(dlg)
        timer.setInterval(_LIVE_REFRESH_INTERVAL_MS)
        timer.timeout.connect(_refresh_live)
        timer.start()

    btn_row = QHBoxLayout(); btn_row.addStretch()

    if is_resumable:
        def _on_resume_clicked():
            from ui.dialogs import RunProgressDialog
            dlg.accept()
            RunProgressDialog(pipeline_id, pname, parent, resume_from_run_id=run_id).exec()

        btn_resume = QPushButton("Reprendre depuis l'échec")
        btn_resume.setObjectName("secondary")
        btn_resume.setFixedHeight(34)
        btn_resume.clicked.connect(_on_resume_clicked)
        btn_row.addWidget(btn_resume)

    btn_close = QPushButton("Fermer")
    btn_close.setFixedHeight(34)
    btn_close.clicked.connect(dlg.accept)
    btn_row.addWidget(btn_close)
    vl.addLayout(btn_row)

    dlg.exec()
