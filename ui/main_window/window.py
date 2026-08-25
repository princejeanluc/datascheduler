"""
DataScheduler — ui/main_window/window.py
Fenêtre principale (navigation latérale) + point d'entrée run().
"""

import sys

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QStackedWidget, QFrame, QStatusBar,
)
from PySide6.QtCore import QSize, QTimer
from PySide6.QtGui import QColor, QPalette, QShortcut, QKeySequence
from ui.styles import COLORS
from .widgets import _icon, NavButton, NAV_WIDTH, HEADER_H, GLOBAL_STYLE
from version import __version__
from .scheduler_bridge import SchedulerNotifier
from .dashboard_view import DashboardView
from .pipelines_view import PipelinesView
from .connections_view import ConnectionsView
from .queries_view import QueriesView
from .history_view import HistoryView
from .resources_view import ResourcesView
from .settings_view import SettingsView


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"KULU v{__version__}")
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

        # Rattrapage des pipelines manqués (chantier dédié) — affiché une seule fois, après que
        # la fenêtre principale soit réellement peinte (QTimer.singleShot(0, ...), jamais avant
        # window.show() dans run()). core.missed_runs a déjà été peuplé dans main.py, avant
        # init_scheduler() — cette fenêtre se contente de le consulter, comme toute autre vue.
        from core.missed_runs import get_pending
        if get_pending():
            QTimer.singleShot(0, self._show_missed_pipelines_dialog)

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
        # Import différé (pas en tête de fichier) : ui.help.help_view réutilise les helpers de
        # ce module (ui.main_window.widgets) — un import en tête de fichier créerait un cycle
        # d'import selon l'ordre d'import initial (ui.help avant ui.main_window).
        from ui.help import HelpView
        self._views = [
            DashboardView(),
            PipelinesView(),
            ConnectionsView(),
            QueriesView(),
            HistoryView(),
            ResourcesView(),
            SettingsView(),
            HelpView(),
        ]
        for v in self._views:
            self._stack.addWidget(v)
        root.addWidget(self._stack, stretch=1)

        self._views[0].navigate_to_history.connect(self._on_dashboard_navigate_to_history)
        self._views[0].navigate_to_settings.connect(self._on_dashboard_navigate_to_settings)

        # Statut bar
        status = QStatusBar()
        status.setStyleSheet(f"background: {COLORS['bg_panel']}; color: {COLORS['text_dim']}; border-top: 1px solid {COLORS['border']};")
        status.showMessage("  KULU  •  Prêt")
        self.setStatusBar(status)

        self._navigate(0)   # Dashboard par défaut

        QShortcut(QKeySequence("F5"), self, activated=self._refresh_current_view)

    def _refresh_current_view(self):
        view = self._views[self._stack.currentIndex()]
        if hasattr(view, "refresh"):
            view.refresh()
        self.statusBar().showMessage("  Vue actualisée", 2_000)

    def _show_missed_pipelines_dialog(self):
        from core.missed_runs import get_pending
        from ui.dialogs import MissedPipelinesDialog

        missed = get_pending()
        if not missed:
            return
        MissedPipelinesDialog(self, missed).exec()
        # Rafraîchit le Dashboard immédiatement — reflète ce qui a été lancé (résolu) vs laissé
        # en attente (bandeau), sans attendre son propre cycle de rafraîchissement périodique.
        self._views[0].refresh()

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
        logo_layout.setContentsMargins(18, 0, 18, 0)
        logo_layout.setSpacing(10)
        from ui.icons import logo_icon as _logo_icon
        logo_icon = QLabel()
        logo_icon.setFixedSize(22, 22)
        logo_icon.setPixmap(_logo_icon(COLORS["accent"], size=22).pixmap(22, 22))
        logo_icon.setStyleSheet("background: transparent; border: none;")
        logo_lbl = QLabel("KULU")
        logo_lbl.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 14px; font-weight: 700; "
            f"background: transparent; border: none; letter-spacing: 0.5px;"
        )
        logo_layout.addWidget(logo_icon)
        logo_layout.addWidget(logo_lbl)
        layout.addWidget(logo_widget)

        # Boutons de navigation
        nav_items = [
            ("Dashboard",    "dashboard",    0),
            ("Pipelines",    "pipelines",    1),
            ("Connexions",   "connexions",   2),
            ("Requêtes SQL", "requetes_sql", 3),
            ("Historique",   "historique",   4),
            ("Ressources",   "ressources",   5),
            ("Paramètres",   "parametres",   6),
            ("Aide",         "aide",         7),
        ]
        self._nav_buttons: list[NavButton] = []
        for label, icon, idx in nav_items:
            btn = NavButton(label, icon)
            btn.clicked.connect(lambda checked, i=idx: self._navigate(i))
            self._nav_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        # Version en bas
        version_lbl = QLabel(f"v{__version__}")
        version_lbl.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; padding: 12px 18px; background: transparent;")
        layout.addWidget(version_lbl)

        return panel

    def _on_dashboard_navigate_to_history(self, status: str):
        self._navigate(4)
        self._views[4].set_status_filter(status)

    def _on_dashboard_navigate_to_settings(self, category: str):
        self._navigate(6)
        self._views[6].select_category(category)

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

    from ui.fonts import register_app_fonts
    register_app_fonts()

    app.setStyleSheet(GLOBAL_STYLE)

    # KULU.spec (icon=...) couvre l'icône de l'exécutable (Explorateur, tuile avant
    # lancement) — Qt ne la reprend pas automatiquement pour la fenêtre une fois affichée
    # (barre de titre, bouton de la barre des tâches pendant l'exécution, Alt-Tab).
    from ui.branding import app_icon
    app.setWindowIcon(app_icon())

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
