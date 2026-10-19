"""
DataScheduler — ui/main_window/window.py
Fenêtre principale (navigation latérale) + point d'entrée run().
"""

import sys

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout,
    QStackedWidget, QFrame, QStatusBar,
)
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPalette, QShortcut, QKeySequence
from ui.styles import COLORS
from .widgets import NavRail, GLOBAL_STYLE
from version import __version__
from .scheduler_bridge import SchedulerNotifier
from .dashboard_view import DashboardView
from .pipelines_view import PipelinesView
from .connections_view import ConnectionsView
from .queries_view import QueriesView
from .history_view import HistoryView
from .resources_view import ResourcesView
from .settings_view import SettingsView
from .atelier_pipelines_view import AtelierPipelinesView


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
        # Composant autonome (chantier repli du menu) — voir NavRail (ui/main_window/widgets.py)
        # pour pourquoi cette extraction, pas seulement une préférence de style.
        from database import db_manager as db
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
        self._nav_rail = NavRail(nav_items, initial_collapsed=db.get_app_settings().nav_collapsed)
        self._nav_rail.navigate_requested.connect(self._navigate)
        self._nav_rail.collapsed_changed.connect(
            lambda collapsed: db.update_app_settings(nav_collapsed=collapsed)
        )
        root.addWidget(self._nav_rail)

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
            # Atelier Pipelines (chantier Atelier Pipelines, écran 2) — 9e vue, indice 8, HORS
            # des 8 indices connus de nav_items ci-dessus : jamais une entrée de la nav rail,
            # atteinte uniquement via open_atelier() (voir plus bas). set_active_index(8) sur
            # NavRail ne surligne simplement aucun des 8 boutons existants (aucune modification
            # de NavRail nécessaire).
            AtelierPipelinesView(),
        ]
        for v in self._views:
            self._stack.addWidget(v)
        root.addWidget(self._stack, stretch=1)

        self._views[0].navigate_to_history.connect(self._on_dashboard_navigate_to_history)
        self._views[0].navigate_to_settings.connect(self._on_dashboard_navigate_to_settings)
        # A1 : "+ Nouveau pipeline" sur Aujourd'hui délègue directement au point d'entrée de
        # création de PipelinesView (QInputDialog puis open_atelier_requested, déjà câblé
        # ci-dessous) — pas de duplication de logique.
        self._views[0].new_pipeline_requested.connect(self._views[1]._on_new_pipeline)
        # A9/A10 : "Ouvrir dans l'Atelier" depuis les panneaux latéraux d'Aujourd'hui.
        self._views[0].open_atelier_requested.connect(self.open_atelier)
        # A12 : accueil "premier pipeline" — navigation directe (Connexions/Requêtes SQL/Aide)
        # ou appel du même point d'entrée privé que leurs boutons respectifs dans PipelinesView
        # (déjà le patron de new_pipeline_requested ci-dessus).
        self._views[0].open_connections_requested.connect(lambda: self._navigate(2))
        self._views[0].open_sql_editor_requested.connect(lambda: self._navigate(3))
        self._views[0].start_from_template_requested.connect(self._views[1]._on_start_from_template)
        self._views[0].import_pipeline_requested.connect(self._views[1]._on_import_pipeline)
        self._views[0].open_help_requested.connect(lambda: self._navigate(7))
        self._views[1].open_atelier_requested.connect(self.open_atelier)
        self._views[4].open_atelier_requested.connect(self.open_atelier)
        self._views[8].back_requested.connect(lambda: self._navigate(1))

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

    def _on_dashboard_navigate_to_history(self, status: str):
        self._navigate(4)
        self._views[4].set_status_filter(status)

    def _on_dashboard_navigate_to_settings(self, category: str):
        self._navigate(6)
        self._views[6].select_category(category)

    def open_atelier(self, pipeline_id: int, highlight_step_key: str | None = None,
                      is_new_pipeline: bool = False):
        """Ouvre l'Atelier Pipelines (chantier Atelier Pipelines, écran 2) sur `pipeline_id` —
        point d'entrée unique depuis PipelinesView.open_atelier_requested/
        HistoryView.open_atelier_requested. open_pipeline() AVANT _navigate(8), jamais l'inverse
        : _navigate() appelle view.refresh() en atterrissant, qui ne doit rafraîchir que la
        sidebar (voir AtelierPipelinesView.refresh()) — le canevas/panneau doivent déjà être en
        place à ce moment-là."""
        self._views[8].open_pipeline(pipeline_id, highlight_step_key=highlight_step_key,
                                      is_new_pipeline=is_new_pipeline)
        self._navigate(8)

    def _navigate(self, index: int):
        self._stack.setCurrentIndex(index)
        self._nav_rail.set_active_index(index)
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
    # ToolTipBase/ToolTipText jamais définis auparavant — sur certaines machines, QToolTip
    # retombe alors sur le chrome natif de l'OS (thème sombre/clair Windows) au lieu de la
    # palette de l'appli, texte et fond pouvant venir de deux sources différentes et se
    # confondre. Défini ici en complément de la règle QSS QToolTip (GLOBAL_STYLE) — la palette
    # est le filet de sécurité si un widget échappait au style sheet.
    palette.setColor(QPalette.ToolTipBase,     QColor(COLORS["bg_card"]))
    palette.setColor(QPalette.ToolTipText,     QColor(COLORS["text_main"]))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
