"""
DataScheduler — ui/main_window/dashboard_view.py
Vue Dashboard : état des pipelines + dernières exécutions.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox,
)
from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QFont, QColor
from ui.styles import COLORS
from .widgets import _icon, _configure_columns, _make_empty_label, StatCard, _STATUS_BADGE, _status_str, FONT_MONO
from .activity_chart import ActivityChartWidget


class DashboardView(QWidget):
    navigate_to_history = Signal(str)

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
        btn_notifications = QPushButton("  Notifications"); btn_notifications.setObjectName("secondary")
        btn_notifications.setFixedHeight(36)
        btn_notifications.setIcon(_icon("fa5s.bell", COLORS["text_main"]))
        btn_notifications.setIconSize(QSize(13, 13))
        btn_notifications.clicked.connect(self._on_notifications)
        h_layout.addWidget(btn_notifications)
        btn_run_all = QPushButton("  Tout exécuter"); btn_run_all.setFixedHeight(36)
        btn_run_all.setIcon(_icon("fa5s.bolt", "#000000")); btn_run_all.setIconSize(QSize(14, 14))
        btn_run_all.clicked.connect(self._on_run_all)
        h_layout.addWidget(btn_run_all)
        layout.addWidget(header)

        self._onboarding_banner = QLabel(
            "Bienvenue — commencez par créer vos connexions (Connexions), puis vos requêtes SQL "
            "si besoin (Requêtes SQL), avant de créer votre premier pipeline (Pipelines). "
            "Consultez la section Aide pour un guide pas à pas."
        )
        self._onboarding_banner.setWordWrap(True)
        self._onboarding_banner.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 12px; background: {COLORS['bg_panel']}; "
            f"border: 1px solid {COLORS['border']}; border-left: 3px solid {COLORS['accent']}; "
            f"border-radius: 6px; padding: 12px 16px;"
        )
        self._onboarding_banner.setVisible(False)
        layout.addWidget(self._onboarding_banner)

        stats_row = QHBoxLayout(); stats_row.setSpacing(16)
        self._card_active  = StatCard("Pipelines actifs", "—", "configurés")
        self._card_success = StatCard("Succès (30j)",     "—", "exécutions", COLORS["success"], clickable=True)
        self._card_failed  = StatCard("Échecs (30j)",     "—", "exécutions", COLORS["danger"], clickable=True)
        self._card_next    = StatCard("Prochaine exéc.",  "—", "pipeline")
        self._card_success.setToolTip("Voir les exécutions réussies dans l'Historique")
        self._card_failed.setToolTip("Voir les échecs dans l'Historique")
        self._card_success.clicked.connect(lambda: self.navigate_to_history.emit("SUCCESS"))
        self._card_failed.clicked.connect(lambda: self.navigate_to_history.emit("FAILED"))
        for c in (self._card_active, self._card_success, self._card_failed, self._card_next):
            stats_row.addWidget(c)
        layout.addLayout(stats_row)

        sep = QFrame(); sep.setObjectName("separator"); sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        lbl_activity = QLabel("Activité (30 derniers jours)")
        lbl_activity.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {COLORS['text_main']};")
        layout.addWidget(lbl_activity)

        self.chart = ActivityChartWidget()
        self.chart.setFixedHeight(150)
        layout.addWidget(self.chart)

        sep2 = QFrame(); sep2.setObjectName("separator"); sep2.setFrameShape(QFrame.HLine)
        layout.addWidget(sep2)

        lbl_recent = QLabel("Dernières exécutions")
        lbl_recent.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {COLORS['text_main']};")
        layout.addWidget(lbl_recent)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Pipeline", "Statut", "Lignes", "Durée", "Date", "Fichier déposé"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        _configure_columns(self.table, stretch_cols={0, 5})
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 130)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.setFixedHeight(200)
        layout.addWidget(self.table)

        self._empty_label = _make_empty_label(
            "Aucune exécution pour l'instant — les runs planifiés ou manuels apparaîtront ici."
        )
        self._empty_label.setFixedHeight(200)
        self._empty_label.setVisible(False)
        layout.addWidget(self._empty_label)

        self.refresh()

    def refresh(self):
        from database import db_manager as db
        from datetime import datetime, timedelta, timezone

        pipelines = db.get_pipelines()
        self._card_active.set_value(str(len(pipelines)))
        self._onboarding_banner.setVisible(not pipelines)

        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
        all_runs = db.get_recent_runs(limit=500)
        recent = [r for r in all_runs if r.started_at and r.started_at >= cutoff]
        self._card_success.set_value(str(sum(1 for r in recent if _status_str(r.status) == "SUCCESS")))
        self._card_failed.set_value(str(sum(1 for r in recent if _status_str(r.status) == "FAILED")))

        self.chart.set_data(db.get_run_counts_by_day(days=30))

        upcoming = [p for p in pipelines if p.next_run_at]
        if upcoming:
            nxt = min(upcoming, key=lambda p: p.next_run_at)
            self._card_next.set_value(nxt.next_run_at.strftime("%H:%M"))
            self._card_next.set_subtitle(nxt.name)
        else:
            self._card_next.set_value("—")
            self._card_next.set_subtitle("aucun planifié")

        latest = db.get_recent_runs(limit=20)
        self.table.setVisible(bool(latest))
        self._empty_label.setVisible(not latest)
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
                    # Le nom du pipeline ressort en rouge sur un échec — pas seulement le badge
                    # de statut — pour repérer un échec en un coup d'œil en parcourant la liste,
                    # avec le message d'erreur en infobulle pour un premier diagnostic sans
                    # ouvrir l'historique complet.
                    if c_idx == 0 and st == "FAILED":
                        item.setForeground(QColor(COLORS["danger"]))
                        font = item.font(); font.setBold(True); item.setFont(font)
                        if run.error_message:
                            item.setToolTip(run.error_message)
                    else:
                        item.setForeground(QColor(COLORS["text_dim"] if c_idx == 5 else COLORS["text_main"]))
                        if c_idx == 5:
                            item.setFont(QFont(FONT_MONO, 11))
                    self.table.setItem(r_idx, c_idx, item)
            self.table.setRowHeight(r_idx, 44)


    def _on_notifications(self):
        from ui.dialogs import NotificationSettingsDialog
        NotificationSettingsDialog(self).exec()

    def _on_run_all(self):
        try:
            from core.scheduler import get_scheduler
            from database import db_manager as db
            pipelines = db.get_pipelines(active_only=True)
            if not pipelines:
                QMessageBox.information(self, "Tout exécuter", "Aucun pipeline actif à lancer.")
                return
            reply = QMessageBox.question(
                self, "Tout exécuter",
                f"Lancer {len(pipelines)} pipeline(s) actif(s) maintenant ?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
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
