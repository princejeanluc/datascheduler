"""
DataScheduler — ui/main_window/remote_run_dialog.py
Dialogue de suivi d'un lancement manuel délégué au worker en arrière-plan (chantier exécution en
arrière-plan) — pendant qu'un RUN_NOW est en attente d'être ramassé par le worker (jusqu'à ~3s,
voir core/scheduler.py::_poll_worker_commands), puis une fois le run démarré, PipelineRun.
log_text/current_step_label sont relus depuis la base (déjà écrits en continu par run_pipeline(),
chantier N) — même mécanisme de rafraîchissement incrémental que run_log_dialog.py, juste un
point d'entrée différent (on ne connaît pas encore le run_id au moment d'ouvrir ce dialogue).

Pas de barre de progression numérique (contrairement à RunProgressDialog) : le pourcentage
n'existe que comme argument transitoire du callback on_progress() de run_pipeline(), jamais
persisté en base — seuls le libellé d'étape et le log le sont, donc c'est tout ce qu'un dialogue
qui ne fait QUE lire la base peut afficher.
"""

import json
from datetime import datetime

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QLabel, QPushButton
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from ui.styles import COLORS, DIALOG_STYLE
from .widgets import _status_str, FONT_MONO


def _title_color(status: str) -> str:
    if status == "SUCCESS":
        return COLORS["success"]
    if status == "FAILED":
        return COLORS["danger"]
    return COLORS["accent"]


def open_remote_run_dialog(parent, pipeline_id: int, pipeline_name: str) -> None:
    from database import db_manager as db

    enqueued_at = datetime.utcnow()

    dlg = QDialog(parent)
    dlg.setWindowTitle(f"Exécution (arrière-plan) — {pipeline_name}")
    dlg.setMinimumSize(640, 420)
    dlg.setStyleSheet(DIALOG_STYLE)

    vl = QVBoxLayout(dlg)
    vl.setContentsMargins(20, 16, 20, 16)
    vl.setSpacing(12)

    lbl_title = QLabel(f"{pipeline_name}  ·  En attente du worker…")
    lbl_title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORS['accent']};")
    vl.addWidget(lbl_title)

    lbl_step = QLabel("")
    lbl_step.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
    vl.addWidget(lbl_step)

    # Étapes actives en parallèle (chantier parallélisme intra-pipeline) — masqué tant qu'au
    # plus une étape est active à la fois (lbl_step ci-dessus suffit alors), même convention que
    # ui/dialogs/run_progress_dialog.py::lbl_active_steps.
    lbl_active_steps = QLabel("")
    lbl_active_steps.setWordWrap(True)
    lbl_active_steps.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
    lbl_active_steps.setVisible(False)
    vl.addWidget(lbl_active_steps)

    lbl_err = QLabel("")
    lbl_err.setStyleSheet(f"color: {COLORS['danger']}; font-size: 12px;")
    lbl_err.setWordWrap(True)
    lbl_err.setVisible(False)
    vl.addWidget(lbl_err)

    txt = QTextEdit()
    txt.setReadOnly(True)
    txt.setFont(QFont(FONT_MONO, 11))
    txt.setStyleSheet(
        f"background: {COLORS['bg_main']}; color: {COLORS['text_main']}; "
        f"border: 1px solid {COLORS['border']}; border-radius: 4px;"
    )
    txt.setPlainText("En attente que le worker en arrière-plan démarre l'exécution…")
    vl.addWidget(txt)

    btn_row = QHBoxLayout(); btn_row.addStretch()
    btn_stop = QPushButton("Arrêter")
    btn_stop.setObjectName("danger")
    btn_stop.setFixedHeight(34)
    btn_row.addWidget(btn_stop)
    btn_close = QPushButton("Fermer")
    btn_close.setFixedHeight(34)
    btn_close.clicked.connect(dlg.accept)
    btn_row.addWidget(btn_close)
    vl.addLayout(btn_row)

    state = {"run_id": None, "status": None}

    def _on_stop_clicked():
        from core.execution_mode import request_cancel_run
        request_cancel_run(pipeline_id)
        btn_stop.setEnabled(False)
        lbl_step.setText("Arrêt demandé — prend effet à la fin de l'étape en cours, pas instantanément.")

    btn_stop.clicked.connect(_on_stop_clicked)

    def _tick():
        if state["run_id"] is None:
            # Toujours en attente que le worker ramasse la commande RUN_NOW et crée le run.
            runs = db.get_runs(pipeline_id, limit=1)
            if not runs or not runs[0].started_at or runs[0].started_at < enqueued_at:
                return
            state["run_id"] = runs[0].id
            state["status"] = "RUNNING"
            lbl_title.setText(f"{pipeline_name}  ·  RUNNING")
            lbl_title.setStyleSheet(
                f"font-size: 15px; font-weight: 700; color: {_title_color('RUNNING')};")
            txt.setPlainText("")

        run = db.get_run(state["run_id"])
        if not run:
            timer.stop()
            return

        new_log = run.log_text or ""
        if new_log != txt.toPlainText():
            bar = txt.verticalScrollBar()
            at_bottom = bar.value() >= bar.maximum() - 4
            txt.setPlainText(new_log)
            if at_bottom:
                bar.setValue(bar.maximum())

        step_label = run.current_step_label or ""
        lbl_step.setText(f"Étape en cours : {step_label}" if step_label else "")

        active_steps = {}
        if run.active_steps_json:
            try:
                active_steps = json.loads(run.active_steps_json)
            except (ValueError, TypeError):
                active_steps = {}
        if len(active_steps) > 1:
            lines = [f"• {info.get('label') or key}" for key, info in active_steps.items()]
            lbl_active_steps.setText("Étapes en cours en parallèle :\n" + "\n".join(lines))
            lbl_active_steps.setVisible(True)
        else:
            lbl_active_steps.setVisible(False)

        new_status = _status_str(run.status)
        if new_status != state["status"]:
            state["status"] = new_status
            lbl_title.setText(f"{pipeline_name}  ·  {new_status}")
            lbl_title.setStyleSheet(
                f"font-size: 15px; font-weight: 700; color: {_title_color(new_status)};")
            if run.error_message:
                lbl_err.setText(f"Erreur : {run.error_message}")
                lbl_err.setVisible(True)
            if new_status != "RUNNING":
                btn_stop.setVisible(False)
                timer.stop()

    timer = QTimer(dlg)
    timer.setInterval(db.get_app_settings().live_log_refresh_s * 1000)
    timer.timeout.connect(_tick)
    timer.start()

    dlg.exec()
