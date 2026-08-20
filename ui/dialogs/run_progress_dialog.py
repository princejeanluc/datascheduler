"""
DataScheduler — ui/dialogs/run_progress_dialog.py
Dialogue de suivi d'exécution d'un pipeline en temps réel.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QPlainTextEdit, QProgressBar,
)
from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtGui import QFont
from ui.styles import COLORS, DIALOG_STYLE, FONT_MONO

# Fermer le dialogue pendant l'exécution ne doit PAS interrompre le pipeline (voir la docstring
# de RunProgressDialog) — mais un widget Qt parenté ne suffit pas à lui seul à protéger son
# attribut Python self._thread (et les connexions de signaux vers ses méthodes liées) du ramasse-
# miettes une fois qu'aucune variable Python ne référence plus le dialogue (confirmé en pratique :
# "QThread: Destroyed while thread is still running" sans ce filet). Référence forte explicite,
# retirée dès que le thread concerné se termine (_on_finished).
_background_runs: set = set()


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

    Peut être fermé à tout moment pendant l'exécution — "Fermer" cache juste la fenêtre, le
    pipeline continue de tourner en arrière-plan (visible ensuite via le badge "RUNNING" de
    PipelinesView/Dashboard, interruptible depuis son menu "…") ; "Arrêter" demande
    l'interruption coopérative (même mécanisme que pipelines_view.py::_on_run_pipeline lors d'une
    relance sur un run déjà en cours), qui prend effet à la fin de l'étape en cours, pas
    instantanément.

    Fermer sans arrêter : un parent Qt (voir les appelants) protège le WIDGET de la destruction,
    mais PAS l'attribut Python self._thread ni les connexions de signaux vers les méthodes liées
    de CE dialogue — sans rien de plus, le ramasse-miettes Python peut les récupérer dès qu'aucune
    variable ne référence plus le dialogue (confirmé en pratique par un crash réel : "QThread:
    Destroyed while thread is still running"). D'où _background_runs (module-level) : référence
    forte explicite tant que le thread tourne encore au moment de la fermeture, retirée une fois
    le run terminé (_on_finished).
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

        # Étapes actives en parallèle (chantier parallélisme intra-pipeline) — masqué par défaut,
        # ne s'affiche que si ce pipeline a le parallélisme activé ET que plus d'une étape tourne
        # réellement en même temps (voir _poll_active_steps) ; lbl_step/progress_bar ci-dessus
        # restent la vue "dernière étape en date", inchangée, pour tout run non-parallèle.
        self.lbl_active_steps = QLabel("")
        self.lbl_active_steps.setWordWrap(True)
        self.lbl_active_steps.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
        self.lbl_active_steps.setVisible(False)
        root.addWidget(self.lbl_active_steps)

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
        self.btn_stop = QPushButton("Arrêter")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.setFixedHeight(34)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        btn_row.addWidget(self.btn_stop)
        self.btn_resume = QPushButton("Reprendre depuis l'échec")
        self.btn_resume.setObjectName("secondary")
        self.btn_resume.setFixedHeight(34)
        self.btn_resume.setVisible(False)
        self.btn_resume.clicked.connect(self._on_resume_clicked)
        btn_row.addWidget(self.btn_resume)
        self.btn_close = QPushButton("Fermer")
        self.btn_close.setFixedHeight(34)
        self.btn_close.clicked.connect(self._on_close_clicked)
        btn_row.addWidget(self.btn_close)
        root.addLayout(btn_row)

    def _start(self, pipeline_id: int, resume_from_run_id: int | None = None):
        from datetime import datetime

        self._thread = RunProgressThread(pipeline_id, resume_from_run_id)
        self._thread.progress_signal.connect(self._on_progress)
        self._thread.finished_signal.connect(self._on_finished)
        self._thread.start()

        # Sondage indépendant du signal ci-dessus (chantier parallélisme intra-pipeline) —
        # progress_signal ne porte que la DERNIÈRE étape ayant tiqué, insuffisant pour afficher
        # "N étapes en cours" (voir core/pipeline.py::_execute_graph_parallel, qui persiste déjà
        # cet état complet dans PipelineRun.active_steps_json). Même patron de découverte du run
        # que ui/main_window/remote_run_dialog.py : on ne connaît pas encore son id à l'ouverture.
        from database import db_manager as db
        self._active_steps_enqueued_at = datetime.utcnow()
        self._active_steps_run_id = None
        interval_s = max(1, db.get_app_settings().live_log_refresh_s)
        self._active_steps_timer = QTimer(self)
        self._active_steps_timer.setInterval(interval_s * 1000)
        self._active_steps_timer.timeout.connect(self._poll_active_steps)
        self._active_steps_timer.start()

    def _poll_active_steps(self):
        import json
        from database import db_manager as db

        if self._active_steps_run_id is None:
            runs = db.get_runs(self._pipeline_id, limit=1)
            if not runs or not runs[0].started_at or runs[0].started_at < self._active_steps_enqueued_at:
                return
            self._active_steps_run_id = runs[0].id

        run = db.get_run(self._active_steps_run_id)
        if not run or not run.active_steps_json:
            self.lbl_active_steps.setVisible(False)
            return
        try:
            active = json.loads(run.active_steps_json)
        except (ValueError, TypeError):
            return
        if len(active) <= 1:
            # Une seule étape à la fois : lbl_step ci-dessus la montre déjà, pas besoin de
            # dupliquer l'information.
            self.lbl_active_steps.setVisible(False)
            return
        lines = [f"• {info.get('label') or key}" for key, info in active.items()]
        self.lbl_active_steps.setText("Étapes en cours en parallèle :\n" + "\n".join(lines))
        self.lbl_active_steps.setVisible(True)

    def _on_progress(self, step: str, pct: int):
        self.lbl_step.setText(step)
        self.progress_bar.setValue(pct)
        self.log_area.appendPlainText(f"  {step}")

    def _on_close_clicked(self):
        if self._thread is not None and self._thread.isRunning():
            _background_runs.add(self)   # voir le commentaire sur _background_runs en tête de fichier
        self.accept()

    def closeEvent(self, event):
        if self._thread is not None and self._thread.isRunning():
            _background_runs.add(self)
        super().closeEvent(event)

    def _on_finished(self, result):
        _background_runs.discard(self)
        self.btn_stop.setVisible(False)
        if getattr(self, "_active_steps_timer", None) is not None:
            self._active_steps_timer.stop()
        self.lbl_active_steps.setVisible(False)
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

    def _on_stop_clicked(self):
        from core.pipeline import request_cancel
        request_cancel(self._pipeline_id)
        self.btn_stop.setEnabled(False)
        self.lbl_step.setText(
            "Arrêt demandé — prend effet à la fin de l'étape en cours, pas instantanément."
        )
