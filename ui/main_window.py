"""
DataScheduler — ui/main_window.py
Fenêtre principale PySide6 avec navigation latérale.

Vues :
  • Dashboard    — état des pipelines + dernières exécutions
  • Pipelines    — liste + création
  • Connexions   — profils Oracle et FTP
  • Requêtes SQL — bibliothèque de requêtes
  • Historique   — logs détaillés

Design : industriel / utilitaire sombre — lisible et professionnel.
"""

import sys
import qtawesome as qta
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout,
    QVBoxLayout, QLabel, QPushButton, QStackedWidget,
    QFrame, QSizePolicy, QSpacerItem, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMessageBox, QStatusBar,
)
from PySide6.QtCore import Qt, QSize, Signal, QThread, QTimer, QObject
from PySide6.QtGui import QFont, QColor, QPalette, QIcon, QPixmap

from ui.styles import COLORS

# ──────────────────────────────────────────────
#  HELPERS ICÔNES
# ──────────────────────────────────────────────

def _icon(name: str, color: str) -> QIcon:
    return qta.icon(name, color=color)

def _action_btn(icon_name: str, object_name: str = "", tooltip: str = "",
                size: tuple = (28, 26), icon_color: str = None) -> QPushButton:
    """Crée un bouton carré icône-seul pour les tableaux d'actions."""
    btn = QPushButton()
    if object_name:
        btn.setObjectName(object_name)
    if tooltip:
        btn.setToolTip(tooltip)
    btn.setFixedSize(*size)
    color = icon_color or (COLORS["danger"] if object_name == "danger" else COLORS["text_main"])
    btn.setIcon(_icon(icon_name, color))
    btn.setIconSize(QSize(14, 14))
    return btn

# ──────────────────────────────────────────────
#  CONSTANTES
# ──────────────────────────────────────────────

NAV_WIDTH   = 220
HEADER_H    = 52
FONT_MONO   = "Consolas"
FONT_UI     = "Segoe UI"


# ──────────────────────────────────────────────
#  STYLES CSS GLOBAUX
# ──────────────────────────────────────────────

GLOBAL_STYLE = f"""
QWidget {{
    background-color: {COLORS['bg_main']};
    color: {COLORS['text_main']};
    font-family: "{FONT_UI}", "Helvetica Neue", sans-serif;
    font-size: 13px;
}}

/* ── Scrollbar ── */
QScrollBar:vertical {{
    background: {COLORS['bg_panel']};
    width: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {COLORS['border']};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLORS['accent']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

/* ── Tableau ── */
QTableWidget {{
    background-color: {COLORS['bg_panel']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    gridline-color: {COLORS['border']};
    selection-background-color: {COLORS['bg_active']};
}}
QTableWidget::item {{
    padding: 8px 12px;
    border: none;
}}
QTableWidget::item:selected {{
    background-color: {COLORS['bg_active']};
    color: {COLORS['text_main']};
    border-left: 2px solid {COLORS['accent']};
}}
QHeaderView::section {{
    background-color: {COLORS['bg_card']};
    color: {COLORS['text_dim']};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
    padding: 8px 12px;
    border: none;
    border-bottom: 2px solid {COLORS['accent']};
}}

/* ── Boutons ── */
QPushButton {{
    background-color: {COLORS['accent']};
    color: #000000;
    border: none;
    border-radius: 4px;
    padding: 8px 18px;
    font-weight: 700;
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: {COLORS['accent_pale']};
}}
QPushButton:pressed {{
    background-color: {COLORS['accent_dim']};
    color: white;
}}
QPushButton#secondary {{
    background-color: transparent;
    color: {COLORS['text_main']};
    border: 1px solid {COLORS['border']};
}}
QPushButton#secondary:hover {{
    background-color: {COLORS['bg_hover']};
    border-color: {COLORS['accent']};
    color: {COLORS['accent']};
}}
QPushButton#danger {{
    background-color: transparent;
    color: {COLORS['danger']};
    border: 1px solid {COLORS['danger']};
}}
QPushButton#danger:hover {{
    background-color: {COLORS['danger']};
    color: white;
}}

/* ── Formulaires ── */
QLineEdit, QTextEdit, QComboBox, QSpinBox {{
    background-color: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    padding: 7px 10px;
    color: {COLORS['text_main']};
    font-size: 13px;
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border-color: {COLORS['accent']};
    border-width: 2px;
}}
QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    selection-background-color: {COLORS['bg_active']};
    color: {COLORS['text_main']};
}}

/* ── Étiquettes ── */
QLabel#section_title {{
    font-size: 20px;
    font-weight: 700;
    color: {COLORS['text_main']};
}}
QLabel#subtitle {{
    font-size: 13px;
    color: {COLORS['text_dim']};
}}

/* ── Badges statut ── */
QLabel#badge_success {{
    background-color: rgba(63,185,80,0.12);
    color: {COLORS['success']};
    border-radius: 3px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QLabel#badge_failed {{
    background-color: rgba(248,81,73,0.12);
    color: {COLORS['danger']};
    border-radius: 3px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QLabel#badge_running {{
    background-color: rgba(255,121,0,0.15);
    color: {COLORS['accent']};
    border-radius: 3px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QLabel#badge_idle {{
    background-color: rgba(153,153,153,0.10);
    color: {COLORS['text_dim']};
    border-radius: 3px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}

/* ── Cartes et séparateurs ── */
QFrame#card {{
    background-color: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
}}
QFrame#separator {{
    background-color: {COLORS['border']};
    max-height: 1px;
}}
"""


# ──────────────────────────────────────────────
#  COMPOSANT : BOUTON DE NAVIGATION
# ──────────────────────────────────────────────

class NavButton(QPushButton):
    """Bouton de la barre de navigation latérale."""

    def __init__(self, label: str, icon_name: str = ""):
        super().__init__()
        self._label     = label
        self._icon_name = icon_name
        self._active    = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(44)
        self.setIconSize(QSize(16, 16))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._apply_style()

    def set_active(self, active: bool):
        self._active = active
        self._apply_style()

    def _apply_style(self):
        bg     = COLORS["bg_active"] if self._active else "transparent"
        color  = COLORS["text_main"] if self._active else COLORS["text_dim"]
        border = f"border-left: 3px solid {COLORS['accent']};" if self._active else "border-left: 3px solid transparent;"
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {color};
                {border}
                border-radius: 0px;
                padding: 0px 16px 0px 12px;
                text-align: left;
                font-size: 13px;
                font-weight: {"600" if self._active else "400"};
            }}
            QPushButton:hover {{
                background-color: {COLORS['bg_hover']};
                color: {COLORS['text_main']};
            }}
        """)
        self.setText(f"  {self._label}")
        if self._icon_name:
            self.setIcon(_icon(self._icon_name, color))


# ──────────────────────────────────────────────
#  COMPOSANT : CARTE STAT (Dashboard)
# ──────────────────────────────────────────────

class StatCard(QFrame):
    def __init__(self, title: str, value: str = "—", subtitle: str = "",
                 color: str = None):
        super().__init__()
        self.setObjectName("card")
        self.setFixedHeight(100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(4)

        lbl_title = QLabel(title.upper())
        lbl_title.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; font-weight: 700; letter-spacing: 1px; background: transparent; border: none;")

        self._lbl_value = QLabel(value)
        c = color or COLORS["text_main"]
        self._lbl_value.setStyleSheet(f"color: {c}; font-size: 28px; font-weight: 700; background: transparent; border: none;")

        self._lbl_sub = QLabel(subtitle)
        self._lbl_sub.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; background: transparent; border: none;")

        layout.addWidget(lbl_title)
        layout.addWidget(self._lbl_value)
        layout.addWidget(self._lbl_sub)

    def set_value(self, value: str):
        self._lbl_value.setText(value)

    def set_subtitle(self, text: str):
        self._lbl_sub.setText(text)


# ──────────────────────────────────────────────
#  VUE : DASHBOARD
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
#  PONT THREAD-SAFE : SCHEDULER → UI
# ──────────────────────────────────────────────

class SchedulerNotifier(QObject):
    """
    Reçoit les callbacks APScheduler (thread background) et les
    retransmet comme signaux Qt (traités dans le thread principal).
    """
    job_success = Signal(int, str)   # pipeline_id, remote_path
    job_error   = Signal(int, str)   # pipeline_id, error_msg


_STATUS_BADGE = {
    "SUCCESS": "badge_success",
    "FAILED":  "badge_failed",
    "RUNNING": "badge_running",
    "IDLE":    "badge_idle",
}


def _status_str(val) -> str:
    return val.value if hasattr(val, "value") else str(val or "IDLE")


class DashboardView(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setInterval(30_000)   # 30 secondes
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)

        header = QWidget()
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Dashboard"); title.setObjectName("section_title")
        sub   = QLabel("Vue d'ensemble des pipelines"); sub.setObjectName("subtitle")
        title_col = QVBoxLayout(); title_col.setSpacing(2)
        title_col.addWidget(title); title_col.addWidget(sub)
        h_layout.addLayout(title_col); h_layout.addStretch()
        btn_run_all = QPushButton("  Tout exécuter"); btn_run_all.setFixedHeight(36)
        btn_run_all.setIcon(_icon("fa5s.bolt", "#000000")); btn_run_all.setIconSize(QSize(14, 14))
        btn_run_all.clicked.connect(self._on_run_all)
        h_layout.addWidget(btn_run_all)
        layout.addWidget(header)

        stats_row = QHBoxLayout(); stats_row.setSpacing(16)
        self._card_active  = StatCard("Pipelines actifs", "—", "configurés")
        self._card_success = StatCard("Succès (30j)",     "—", "exécutions", COLORS["success"])
        self._card_failed  = StatCard("Échecs (30j)",     "—", "exécutions", COLORS["danger"])
        self._card_next    = StatCard("Prochaine exéc.",  "—", "pipeline")
        for c in (self._card_active, self._card_success, self._card_failed, self._card_next):
            stats_row.addWidget(c)
        layout.addLayout(stats_row)

        sep = QFrame(); sep.setObjectName("separator"); sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        lbl_recent = QLabel("Dernières exécutions")
        lbl_recent.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {COLORS['text_main']};")
        layout.addWidget(lbl_recent)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Pipeline", "Statut", "Lignes", "Durée", "Date", "Fichier déposé"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.setFixedHeight(200)
        layout.addWidget(self.table)

        self.refresh()

    def refresh(self):
        from database import db_manager as db
        from datetime import datetime, timedelta, timezone

        pipelines = db.get_pipelines()
        self._card_active.set_value(str(len(pipelines)))

        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
        all_runs = db.get_recent_runs(limit=500)
        recent = [r for r in all_runs if r.started_at and r.started_at >= cutoff]
        self._card_success.set_value(str(sum(1 for r in recent if _status_str(r.status) == "SUCCESS")))
        self._card_failed.set_value(str(sum(1 for r in recent if _status_str(r.status) == "FAILED")))

        upcoming = [p for p in pipelines if p.next_run_at]
        if upcoming:
            nxt = min(upcoming, key=lambda p: p.next_run_at)
            self._card_next.set_value(nxt.next_run_at.strftime("%H:%M"))
            self._card_next.set_subtitle(nxt.name)
        else:
            self._card_next.set_value("—")
            self._card_next.set_subtitle("aucun planifié")

        latest = db.get_recent_runs(limit=20)
        self.table.setRowCount(len(latest))
        for r_idx, run in enumerate(latest):
            pname = run.pipeline.name if run.pipeline else str(run.pipeline_id)
            st    = _status_str(run.status)
            dur   = "—"
            if run.duration_seconds is not None:
                m, s = divmod(int(run.duration_seconds), 60)
                dur  = f"{m}m {s:02d}s"
            date_s = run.started_at.strftime("%d/%m/%Y %H:%M") if run.started_at else "—"
            rows_s = f"{run.rows_exported:,}".replace(",", " ") if run.rows_exported else "—"
            cells  = [pname, st, rows_s, dur, date_s, run.remote_path or "—"]
            for c_idx, cell in enumerate(cells):
                if c_idx == 1:
                    badge = QLabel(st); badge.setObjectName(_STATUS_BADGE.get(st, "badge_idle"))
                    badge.setAlignment(Qt.AlignCenter)
                    self.table.setCellWidget(r_idx, c_idx, badge)
                else:
                    item = QTableWidgetItem(cell)
                    item.setForeground(QColor(COLORS["text_dim"] if c_idx == 5 else COLORS["text_main"]))
                    if c_idx == 5:
                        item.setFont(QFont(FONT_MONO, 11))
                    self.table.setItem(r_idx, c_idx, item)
            self.table.setRowHeight(r_idx, 44)


    def _on_run_all(self):
        try:
            from core.scheduler import get_scheduler
            from database import db_manager as db
            pipelines = db.get_pipelines(active_only=True)
            if not pipelines:
                QMessageBox.information(self, "Tout exécuter", "Aucun pipeline actif à lancer.")
                return
            sched = get_scheduler()
            for p in pipelines:
                sched.trigger_now(p.id)
            QMessageBox.information(
                self, "Tout exécuter",
                f"{len(pipelines)} pipeline(s) lancé(s) en arrière-plan."
            )
        except RuntimeError:
            QMessageBox.warning(self, "Scheduler", "Le scheduler n'est pas encore démarré.")


# ──────────────────────────────────────────────
#  VUE : PIPELINES
# ──────────────────────────────────────────────

class PipelinesView(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setInterval(30_000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)

        header = QHBoxLayout()
        title_col = QVBoxLayout(); title_col.setSpacing(2)
        title_col.addWidget(_make_title("Pipelines"))
        title_col.addWidget(_make_subtitle("Orchestration flexible par étapes"))
        header.addLayout(title_col); header.addStretch()
        btn_new = QPushButton("  Nouveau pipeline"); btn_new.setFixedHeight(36)
        btn_new.setIcon(_icon("fa5s.plus", "#000000")); btn_new.setIconSize(QSize(13, 13))
        btn_new.clicked.connect(self._on_new_pipeline)
        header.addWidget(btn_new)
        layout.addLayout(header)

        sep = QFrame(); sep.setObjectName("separator"); sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Nom", "Statut", "Étapes", "Planification", "Prochaine exéc.", "Actions"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        self.refresh()

    def refresh(self):
        from database import db_manager as db
        from ui.step_editor import STEP_META
        pipelines = db.get_pipelines()
        self.table.setRowCount(len(pipelines))
        for r_idx, p in enumerate(pipelines):
            st       = _status_str(p.last_status)
            freq     = _status_str(p.frequency)
            plan     = f"{freq} {p.scheduled_time or ''}".strip()
            next_run = p.next_run_at.strftime("%d/%m/%Y %H:%M") if p.next_run_at else "—"

            # Résumé des étapes
            step_types = [str(s.step_type).replace("StepType.", "") for s in (p.steps or [])]
            steps_str  = " → ".join(
                STEP_META.get(t, {}).get("label", t) for t in step_types
            ) or "—"

            text_color = COLORS["text_dim"] if not p.is_active else COLORS["text_main"]
            cells = [p.name, st, steps_str, plan, next_run]
            for c_idx, cell in enumerate(cells):
                if c_idx == 1:
                    badge_st   = "INACTIF" if not p.is_active else st
                    badge_name = "badge_idle" if not p.is_active else _STATUS_BADGE.get(st, "badge_idle")
                    badge = QLabel(badge_st); badge.setObjectName(badge_name)
                    badge.setAlignment(Qt.AlignCenter)
                    self.table.setCellWidget(r_idx, c_idx, badge)
                else:
                    item = QTableWidgetItem(cell)
                    item.setForeground(QColor(text_color))
                    self.table.setItem(r_idx, c_idx, item)

            pid       = p.id
            is_active = p.is_active
            aw  = QWidget(); al = QHBoxLayout(aw); al.setContentsMargins(4, 4, 4, 4); al.setSpacing(4)
            btn_run = _action_btn("fa5s.play", tooltip="Exécuter maintenant",
                                  icon_color="#000000")
            btn_toggle = _action_btn(
                "fa5s.pause" if is_active else "fa5s.play",
                object_name="secondary",
                tooltip="Désactiver" if is_active else "Activer",
                icon_color=COLORS["text_main"] if is_active else COLORS["success"],
            )
            if not is_active:
                btn_toggle.setStyleSheet(
                    f"QPushButton {{ color: {COLORS['success']}; border: 1px solid {COLORS['success']}; "
                    f"border-radius: 4px; background: transparent; }}"
                    f"QPushButton:hover {{ background: {COLORS['success']}; color: #000; }}"
                )
            btn_edit = _action_btn("fa5s.pencil-alt", object_name="secondary", tooltip="Modifier")
            btn_del  = _action_btn("fa5s.trash-alt",  object_name="danger",    tooltip="Supprimer")
            btn_run.clicked.connect(lambda _, i=pid: self._on_run_pipeline(i))
            btn_toggle.clicked.connect(lambda _, i=pid, a=is_active: self._on_toggle_pipeline(i, a))
            btn_edit.clicked.connect(lambda _, i=pid: self._on_edit_pipeline(i))
            btn_del.clicked.connect(lambda _, i=pid: self._on_delete_pipeline(i))
            al.addWidget(btn_run); al.addWidget(btn_toggle)
            al.addWidget(btn_edit); al.addWidget(btn_del); al.addStretch()
            self.table.setCellWidget(r_idx, 5, aw)
            self.table.setRowHeight(r_idx, 52)

    def _on_new_pipeline(self):
        from ui.step_editor import PipelineEditorDialog
        if PipelineEditorDialog(self).exec():
            self.refresh()

    def _on_edit_pipeline(self, pipeline_id: int):
        from database import db_manager as db
        from ui.step_editor import PipelineEditorDialog
        p = db.get_pipeline(pipeline_id)
        if p and PipelineEditorDialog(self, pipeline=p).exec():
            self.refresh()

    def _on_run_pipeline(self, pipeline_id: int):
        from database import db_manager as db
        from ui.dialogs import RunProgressDialog
        p = db.get_pipeline(pipeline_id)
        if not p:
            return
        RunProgressDialog(pipeline_id, p.name, self).exec()
        self.refresh()

    def _on_delete_pipeline(self, pipeline_id: int):
        from database import db_manager as db
        reply = QMessageBox.question(self, "Supprimer", "Supprimer ce pipeline ?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            db.delete_pipeline(pipeline_id)
            self.refresh()

    def _on_toggle_pipeline(self, pipeline_id: int, currently_active: bool):
        from database import db_manager as db
        new_active = not currently_active
        db.set_pipeline_active(pipeline_id, new_active)
        try:
            from core.scheduler import get_scheduler
            sched = get_scheduler()
            if new_active:
                sched.schedule_pipeline(pipeline_id)
            else:
                sched.remove_pipeline(pipeline_id)
        except RuntimeError:
            pass
        self.refresh()


# ──────────────────────────────────────────────
#  VUE : CONNEXIONS
# ──────────────────────────────────────────────

class ConnectionsView(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)

        layout.addWidget(_make_title("Connexions"))
        layout.addWidget(_make_subtitle("Profils Oracle, FTP et SMTP réutilisables dans les pipelines"))

        sep = QFrame(); sep.setObjectName("separator"); sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        cols = QHBoxLayout(); cols.setSpacing(24)
        cols.addWidget(self._build_oracle_panel())
        cols.addWidget(self._build_ftp_panel())
        cols.addWidget(self._build_smtp_panel())
        layout.addLayout(cols)
        layout.addStretch()

        self.refresh()

    # ── Panels ───────────────────────────────────

    def _build_oracle_panel(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        vl = QVBoxLayout(card); vl.setContentsMargins(20, 18, 20, 18); vl.setSpacing(14)

        top = QHBoxLayout()
        lbl = QLabel("Oracle")
        lbl.setStyleSheet("font-size: 14px; font-weight: 700; background: transparent; border: none;")
        btn = QPushButton("  Nouveau profil Oracle"); btn.setFixedHeight(32)
        btn.setIcon(_icon("fa5s.plus", "#000000")); btn.setIconSize(QSize(12, 12))
        btn.clicked.connect(self._on_new_oracle)
        top.addWidget(lbl); top.addStretch(); top.addWidget(btn)
        vl.addLayout(top)

        hdrs = ["Nom", "Hôte", "Port", "Service / SID", "Utilisateur"]
        self.oracle_table = self._make_table(hdrs)
        vl.addWidget(self.oracle_table)
        return card

    def _build_ftp_panel(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        vl = QVBoxLayout(card); vl.setContentsMargins(20, 18, 20, 18); vl.setSpacing(14)

        top = QHBoxLayout()
        lbl = QLabel("FTP / FTPS / SFTP")
        lbl.setStyleSheet("font-size: 14px; font-weight: 700; background: transparent; border: none;")
        btn = QPushButton("  Nouveau profil FTP"); btn.setFixedHeight(32)
        btn.setIcon(_icon("fa5s.plus", "#000000")); btn.setIconSize(QSize(12, 12))
        btn.clicked.connect(self._on_new_ftp)
        top.addWidget(lbl); top.addStretch(); top.addWidget(btn)
        vl.addLayout(top)

        hdrs = ["Nom", "Hôte", "Port", "Protocole", "Utilisateur"]
        self.ftp_table = self._make_table(hdrs)
        vl.addWidget(self.ftp_table)
        return card

    def _build_smtp_panel(self) -> QFrame:
        card = QFrame(); card.setObjectName("card")
        vl = QVBoxLayout(card); vl.setContentsMargins(20, 18, 20, 18); vl.setSpacing(14)

        top = QHBoxLayout()
        lbl = QLabel("SMTP")
        lbl.setStyleSheet("font-size: 14px; font-weight: 700; background: transparent; border: none;")
        btn = QPushButton("  Nouveau profil SMTP"); btn.setFixedHeight(32)
        btn.setIcon(_icon("fa5s.plus", "#000000")); btn.setIconSize(QSize(12, 12))
        btn.clicked.connect(self._on_new_smtp)
        top.addWidget(lbl); top.addStretch(); top.addWidget(btn)
        vl.addLayout(top)

        hdrs = ["Nom", "Hôte", "Port", "Sécurité", "Expéditeur"]
        self.smtp_table = self._make_table(hdrs)
        vl.addWidget(self.smtp_table)
        return card

    def _make_table(self, headers: list) -> QTableWidget:
        t = QTableWidget(0, len(headers) + 1)
        t.setHorizontalHeaderLabels(headers + [""])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setShowGrid(False)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.horizontalHeader().setSectionResizeMode(len(headers), QHeaderView.Fixed)
        t.setColumnWidth(len(headers), 90)
        return t

    # ── Refresh ──────────────────────────────────

    def refresh(self):
        self._refresh_oracle()
        self._refresh_ftp()
        self._refresh_smtp()

    def _refresh_oracle(self):
        from database import db_manager as db
        profiles = db.get_oracle_profiles()
        self.oracle_table.setRowCount(len(profiles))
        for r_idx, p in enumerate(profiles):
            cells = [p.name, p.host, str(p.port), p.service_name or p.sid or "—", p.username]
            for c_idx, cell in enumerate(cells):
                item = QTableWidgetItem(cell)
                item.setForeground(QColor(COLORS["text_main"]))
                self.oracle_table.setItem(r_idx, c_idx, item)
            pid = p.id
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4); hl.setSpacing(4)
            btn_edit = _action_btn("fa5s.pencil-alt", object_name="secondary", tooltip="Modifier")
            btn_del  = _action_btn("fa5s.trash-alt",  object_name="danger",    tooltip="Supprimer")
            btn_edit.clicked.connect(lambda _, i=pid: self._on_edit_oracle(i))
            btn_del.clicked.connect(lambda _, i=pid: self._on_delete_oracle(i))
            hl.addWidget(btn_edit); hl.addWidget(btn_del); hl.addStretch()
            self.oracle_table.setCellWidget(r_idx, 5, w)
            self.oracle_table.setRowHeight(r_idx, 44)

    def _refresh_ftp(self):
        from database import db_manager as db
        profiles = db.get_ftp_profiles()
        self.ftp_table.setRowCount(len(profiles))
        for r_idx, p in enumerate(profiles):
            protocol = _status_str(p.protocol)
            cells = [p.name, p.host, str(p.port), protocol, p.username]
            for c_idx, cell in enumerate(cells):
                item = QTableWidgetItem(cell)
                item.setForeground(QColor(COLORS["text_main"]))
                self.ftp_table.setItem(r_idx, c_idx, item)
            pid = p.id
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4); hl.setSpacing(4)
            btn_edit = _action_btn("fa5s.pencil-alt", object_name="secondary", tooltip="Modifier")
            btn_del  = _action_btn("fa5s.trash-alt",  object_name="danger",    tooltip="Supprimer")
            btn_edit.clicked.connect(lambda _, i=pid: self._on_edit_ftp(i))
            btn_del.clicked.connect(lambda _, i=pid: self._on_delete_ftp(i))
            hl.addWidget(btn_edit); hl.addWidget(btn_del); hl.addStretch()
            self.ftp_table.setCellWidget(r_idx, 5, w)
            self.ftp_table.setRowHeight(r_idx, 44)

    def _refresh_smtp(self):
        from database import db_manager as db
        profiles = db.get_smtp_profiles()
        self.smtp_table.setRowCount(len(profiles))
        for r_idx, p in enumerate(profiles):
            security = "STARTTLS" if p.use_tls else "Aucune"
            cells = [p.name, p.host, str(p.port), security, p.from_address]
            for c_idx, cell in enumerate(cells):
                item = QTableWidgetItem(cell)
                item.setForeground(QColor(COLORS["text_main"]))
                self.smtp_table.setItem(r_idx, c_idx, item)
            pid = p.id
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4); hl.setSpacing(4)
            btn_edit = _action_btn("fa5s.pencil-alt", object_name="secondary", tooltip="Modifier")
            btn_del  = _action_btn("fa5s.trash-alt",  object_name="danger",    tooltip="Supprimer")
            btn_edit.clicked.connect(lambda _, i=pid: self._on_edit_smtp(i))
            btn_del.clicked.connect(lambda _, i=pid: self._on_delete_smtp(i))
            hl.addWidget(btn_edit); hl.addWidget(btn_del); hl.addStretch()
            self.smtp_table.setCellWidget(r_idx, 5, w)
            self.smtp_table.setRowHeight(r_idx, 44)

    # ── Callbacks ────────────────────────────────

    def _on_new_oracle(self):
        from ui.dialogs import OracleDialog
        dlg = OracleDialog(self)
        if dlg.exec():
            self._refresh_oracle()

    def _on_edit_oracle(self, profile_id: int):
        from database import db_manager as db
        from ui.dialogs import OracleDialog
        p = db.get_oracle_profile(profile_id)
        if p and OracleDialog(self, profile=p).exec():
            self._refresh_oracle()

    def _on_delete_oracle(self, profile_id: int):
        from database import db_manager as db
        reply = QMessageBox.question(self, "Supprimer", "Supprimer ce profil Oracle ?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            db.delete_oracle_profile(profile_id)
            self._refresh_oracle()

    def _on_new_ftp(self):
        from ui.dialogs import FtpDialog
        dlg = FtpDialog(self)
        if dlg.exec():
            self._refresh_ftp()

    def _on_edit_ftp(self, profile_id: int):
        from database import db_manager as db
        from ui.dialogs import FtpDialog
        p = db.get_ftp_profile(profile_id)
        if p and FtpDialog(self, profile=p).exec():
            self._refresh_ftp()

    def _on_delete_ftp(self, profile_id: int):
        from database import db_manager as db
        reply = QMessageBox.question(self, "Supprimer", "Supprimer ce profil FTP ?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            db.delete_ftp_profile(profile_id)
            self._refresh_ftp()

    def _on_new_smtp(self):
        from ui.dialogs import SmtpDialog
        dlg = SmtpDialog(self)
        if dlg.exec():
            self._refresh_smtp()

    def _on_edit_smtp(self, profile_id: int):
        from database import db_manager as db
        from ui.dialogs import SmtpDialog
        p = db.get_smtp_profile(profile_id)
        if p and SmtpDialog(self, profile=p).exec():
            self._refresh_smtp()

    def _on_delete_smtp(self, profile_id: int):
        from database import db_manager as db
        reply = QMessageBox.question(self, "Supprimer", "Supprimer ce profil SMTP ?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            db.delete_smtp_profile(profile_id)
            self._refresh_smtp()


# ──────────────────────────────────────────────
#  VUE : REQUÊTES SQL
# ──────────────────────────────────────────────

class QueriesView(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)

        header = QHBoxLayout()
        col = QVBoxLayout(); col.setSpacing(2)
        col.addWidget(_make_title("Requêtes SQL"))
        col.addWidget(_make_subtitle("Bibliothèque de requêtes réutilisables"))
        header.addLayout(col); header.addStretch()
        btn = QPushButton("  Nouvelle requête"); btn.setFixedHeight(36)
        btn.setIcon(_icon("fa5s.plus", "#000000")); btn.setIconSize(QSize(13, 13))
        btn.clicked.connect(self._on_new_query)
        header.addWidget(btn)
        layout.addLayout(header)

        sep = QFrame(); sep.setObjectName("separator"); sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Nom", "Description", "Profil Oracle associé", "Actions"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
        layout.addStretch()

        self.refresh()

    def refresh(self):
        from database import db_manager as db
        queries = db.get_sql_queries()
        self.table.setRowCount(len(queries))
        for r_idx, q in enumerate(queries):
            oracle_name = q.oracle_profile.name if q.oracle_profile else "—"
            cells = [q.name, q.description or "—", oracle_name]
            for c_idx, cell in enumerate(cells):
                item = QTableWidgetItem(cell)
                item.setForeground(QColor(COLORS["text_main"]))
                self.table.setItem(r_idx, c_idx, item)
            w = QWidget(); hl = QHBoxLayout(w); hl.setContentsMargins(4, 4, 4, 4); hl.setSpacing(6)
            btn_edit = _action_btn("fa5s.pencil-alt", object_name="secondary", tooltip="Modifier",   size=(30, 28))
            btn_del  = _action_btn("fa5s.trash-alt",  object_name="danger",    tooltip="Supprimer",  size=(30, 28))
            qid = q.id
            btn_edit.clicked.connect(lambda _, i=qid: self._on_edit_query(i))
            btn_del.clicked.connect(lambda _, i=qid: self._on_delete_query(i))
            hl.addWidget(btn_edit); hl.addWidget(btn_del); hl.addStretch()
            self.table.setCellWidget(r_idx, 3, w)
            self.table.setRowHeight(r_idx, 48)

    def _on_new_query(self):
        from ui.dialogs import SqlQueryDialog
        if SqlQueryDialog(self).exec():
            self.refresh()

    def _on_edit_query(self, query_id: int):
        from database import db_manager as db
        from ui.dialogs import SqlQueryDialog
        q = db.get_sql_query(query_id)
        if q and SqlQueryDialog(self, query=q).exec():
            self.refresh()

    def _on_delete_query(self, query_id: int):
        from database import db_manager as db
        reply = QMessageBox.question(self, "Supprimer", "Supprimer cette requête ?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            db.delete_sql_query(query_id)
            self.refresh()


# ──────────────────────────────────────────────
#  VUE : HISTORIQUE
# ──────────────────────────────────────────────

class HistoryView(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)

        layout.addWidget(_make_title("Historique"))
        layout.addWidget(_make_subtitle("Journal complet de toutes les exécutions"))

        sep = QFrame(); sep.setObjectName("separator"); sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        self._run_ids = []   # index ligne → run_id

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Pipeline", "Démarré le", "Durée", "Lignes", "Statut", "Fichier déposé"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.doubleClicked.connect(self._on_row_dbl_click)
        layout.addWidget(self.table)
        layout.addStretch()

        self.refresh()

    def refresh(self):
        from database import db_manager as db
        runs = db.get_recent_runs(limit=100)
        self._run_ids = [r.id for r in runs]
        self.table.setRowCount(len(runs))
        for r_idx, run in enumerate(runs):
            pname  = run.pipeline.name if run.pipeline else str(run.pipeline_id)
            st     = _status_str(run.status)
            dur    = "—"
            if run.duration_seconds is not None:
                m, s = divmod(int(run.duration_seconds), 60)
                dur  = f"{m}m {s:02d}s"
            date_s = run.started_at.strftime("%d/%m/%Y %H:%M:%S") if run.started_at else "—"
            rows_s = f"{run.rows_exported:,}".replace(",", " ") if run.rows_exported else "—"
            cells  = [pname, date_s, dur, rows_s, st, run.remote_path or "—"]
            for c_idx, cell in enumerate(cells):
                if c_idx == 4:
                    badge = QLabel(st); badge.setObjectName(_STATUS_BADGE.get(st, "badge_idle"))
                    badge.setAlignment(Qt.AlignCenter)
                    self.table.setCellWidget(r_idx, c_idx, badge)
                else:
                    item = QTableWidgetItem(cell)
                    item.setForeground(QColor(COLORS["text_dim"] if c_idx == 5 else COLORS["text_main"]))
                    if c_idx == 5:
                        item.setFont(QFont(FONT_MONO, 11))
                    self.table.setItem(r_idx, c_idx, item)
            self.table.setRowHeight(r_idx, 44)

    def _on_row_dbl_click(self, index):
        row = index.row()
        if row >= len(self._run_ids):
            return
        from database import db_manager as db
        from database.models import PipelineRun
        with db.get_session() as s:
            run = s.get(PipelineRun, self._run_ids[row])
            if not run:
                return
            pname    = run.pipeline.name if run.pipeline else str(run.pipeline_id)
            st       = _status_str(run.status)
            log_text = run.log_text or "(aucun log enregistré)"
            err_text = run.error_message or ""

        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QLabel, QPushButton
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Log — {pname}")
        dlg.setMinimumSize(640, 420)
        from ui.styles import DIALOG_STYLE
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


# ──────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────

def _make_title(text: str) -> QLabel:
    l = QLabel(text); l.setObjectName("section_title"); return l

def _make_subtitle(text: str) -> QLabel:
    l = QLabel(text); l.setObjectName("subtitle"); return l


# ──────────────────────────────────────────────
#  FENÊTRE PRINCIPALE
# ──────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DataScheduler")
        self.setMinimumSize(1100, 680)
        self.resize(1280, 760)
        self._build_ui()

        # ── Câblage scheduler → UI (thread-safe via signaux Qt) ──
        self._notifier = SchedulerNotifier(self)
        self._notifier.job_success.connect(self._on_scheduler_success)
        self._notifier.job_error.connect(self._on_scheduler_error)
        try:
            from core.scheduler import get_scheduler
            sched = get_scheduler()
            sched._on_job_success = (
                lambda pid, path: self._notifier.job_success.emit(pid, path or "")
            )
            sched._on_job_error = (
                lambda pid, msg: self._notifier.job_error.emit(pid, msg or "")
            )
        except RuntimeError:
            pass

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Barre de navigation latérale ──────────
        self._nav_panel = self._build_nav()
        root.addWidget(self._nav_panel)

        # Séparateur vertical
        vline = QFrame(); vline.setFrameShape(QFrame.VLine)
        vline.setStyleSheet(f"color: {COLORS['border']}; background: {COLORS['border']}; max-width: 1px;")
        root.addWidget(vline)

        # ── Zone de contenu ───────────────────────
        self._stack = QStackedWidget()
        self._views = [
            DashboardView(),
            PipelinesView(),
            ConnectionsView(),
            QueriesView(),
            HistoryView(),
        ]
        for v in self._views:
            self._stack.addWidget(v)
        root.addWidget(self._stack, stretch=1)

        # Statut bar
        status = QStatusBar()
        status.setStyleSheet(f"background: {COLORS['bg_panel']}; color: {COLORS['text_dim']}; border-top: 1px solid {COLORS['border']};")
        status.showMessage("  DataScheduler  •  Prêt")
        self.setStatusBar(status)

        self._navigate(0)   # Dashboard par défaut

    def _build_nav(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(NAV_WIDTH)
        panel.setStyleSheet(f"background-color: {COLORS['bg_panel']};")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo / titre
        logo_widget = QWidget()
        logo_widget.setFixedHeight(HEADER_H)
        logo_widget.setStyleSheet(f"background: {COLORS['bg_panel']}; border-bottom: 1px solid {COLORS['border']};")
        logo_layout = QHBoxLayout(logo_widget)
        logo_layout.setContentsMargins(16, 0, 0, 0)
        logo_layout.setSpacing(10)
        logo_icon = QLabel()
        logo_icon.setPixmap(
            _icon("fa5s.exchange-alt", COLORS["accent"]).pixmap(QSize(18, 18))
        )
        logo_icon.setStyleSheet("background: transparent; border: none;")
        logo_lbl = QLabel("DataScheduler")
        logo_lbl.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 14px; font-weight: 700; "
            f"background: transparent; border: none; letter-spacing: 0.5px;"
        )
        logo_layout.addWidget(logo_icon)
        logo_layout.addWidget(logo_lbl)
        layout.addWidget(logo_widget)

        # Boutons de navigation
        nav_items = [
            ("Dashboard",    "fa5s.tachometer-alt", 0),
            ("Pipelines",    "fa5s.stream",          1),
            ("Connexions",   "fa5s.plug",            2),
            ("Requêtes SQL", "fa5s.database",        3),
            ("Historique",   "fa5s.history",         4),
        ]
        self._nav_buttons: list[NavButton] = []
        for label, icon, idx in nav_items:
            btn = NavButton(label, icon)
            btn.clicked.connect(lambda checked, i=idx: self._navigate(i))
            self._nav_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        # Version en bas
        version_lbl = QLabel("v0.1.0")
        version_lbl.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; padding: 12px 18px; background: transparent;")
        layout.addWidget(version_lbl)

        return panel

    def _navigate(self, index: int):
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.set_active(i == index)
        view = self._views[index]
        if hasattr(view, "refresh"):
            view.refresh()

    def _on_scheduler_success(self, pipeline_id: int, remote_path: str):
        msg = f"  ✓  Pipeline #{pipeline_id} terminé"
        if remote_path:
            msg += f"  →  {remote_path}"
        self.statusBar().showMessage(msg, 10_000)
        self._refresh_views()

    def _on_scheduler_error(self, pipeline_id: int, error_msg: str):
        self.statusBar().showMessage(
            f"  ⚠  Pipeline #{pipeline_id} a échoué : {error_msg}", 15_000
        )
        self._refresh_views()

    def _refresh_views(self):
        for view in self._views:
            if hasattr(view, "refresh"):
                view.refresh()


# ──────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────

def run():
    app = QApplication(sys.argv)
    app.setStyleSheet(GLOBAL_STYLE)

    # Forcer palette sombre au niveau système
    palette = QPalette()
    palette.setColor(QPalette.Window,          QColor(COLORS["bg_main"]))
    palette.setColor(QPalette.WindowText,      QColor(COLORS["text_main"]))
    palette.setColor(QPalette.Base,            QColor(COLORS["bg_card"]))
    palette.setColor(QPalette.AlternateBase,   QColor(COLORS["bg_panel"]))
    palette.setColor(QPalette.Text,            QColor(COLORS["text_main"]))
    palette.setColor(QPalette.ButtonText,      QColor("#000000"))
    palette.setColor(QPalette.Button,          QColor(COLORS["accent"]))
    palette.setColor(QPalette.Highlight,       QColor(COLORS["accent"]))
    palette.setColor(QPalette.HighlightedText, QColor("#000000"))
    palette.setColor(QPalette.Link,            QColor(COLORS["accent"]))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()