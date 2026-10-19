"""
DataScheduler — scripts/capture_views.py
Utilitaire dev (jamais exécuté par l'application) : produit une capture PNG de chaque vue
enregistrée, pour comparer visuellement à sa maquette dans une PR de la refonte (REGLES.md
section 6, point 3). Reprend le snippet de FONDATIONS.md section 5 (QT_QPA_PLATFORM=offscreen,
widget.grab().save(...), résolution 1440×900).

Registre volontairement incomplet au lot 0a : seules les vues instanciables dans leur état par
défaut, sans scénario applicatif particulier, y figurent. Chaque Lot A ajoute au registre les
états que sa fiche d'écran liste (survol, vide, validation...) au moment où ces états existent
réellement dans le code — jamais par anticipation.

Usage : python scripts/capture_views.py [dossier_de_sortie]
(dossier par défaut : docs/refonte/captures/)
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

from ui.fonts import register_app_fonts
from ui.main_window.widgets import GLOBAL_STYLE
from database import db_manager as db

# Largeur de la zone de contenu (1440 moins les 56px de la barre de navigation repliée, voir
# FONDATIONS.md section 5) × hauteur de fenêtre.
CAPTURE_WIDTH = 1440 - 56
CAPTURE_HEIGHT = 900


def _settings_view():
    from ui.main_window.settings_view import SettingsView
    return SettingsView()


def _settings_view_recherche():
    from ui.main_window.settings_view import SettingsView
    view = SettingsView()
    view.inp_search.setText("rafraîch")
    return view


def _settings_view_arriere_plan():
    from ui.main_window.settings_view import SettingsView
    view = SettingsView()
    idx = view.cb_execution_mode.findData("BACKGROUND")
    view.cb_execution_mode.setCurrentIndex(idx)
    return view


def _settings_view_refus():
    """register_logon_task() simulé en échec (politique IT) — même scénario que
    tests/test_settings_view.py::test_failure_banner_shown_when_background_registration_fails."""
    from unittest.mock import patch
    from ui.main_window.settings_view import SettingsView
    view = SettingsView()
    idx = view.cb_execution_mode.findData("BACKGROUND")
    view.cb_execution_mode.setCurrentIndex(idx)
    with patch("core.task_scheduler.register_logon_task", return_value=False):
        view._on_save()
    return view


def _settings_view_notifications_hebdomadaire():
    from ui.main_window.settings_view import SettingsView
    view = SettingsView()
    view.select_category("notifications")
    idx = view.cb_frequency.findData("WEEKLY")
    view.cb_frequency.setCurrentIndex(idx)
    return view


def _settings_view_enregistre():
    from ui.main_window.settings_view import SettingsView
    view = SettingsView()
    view._on_save()
    return view


def _resources_view():
    from ui.main_window.resources_view import ResourcesView
    return ResourcesView()


def _dashboard_view():
    from ui.main_window.dashboard_view import DashboardView
    return DashboardView()


# (nom de fichier sans extension, fabrique de la vue) — un enregistrement par vue/état capturable.
# Parametres-validation n'est pas capturé : son contenu distinctif (bandeau de validation en
# ligne par champ) est C3, gated par la décision P1 — voir docs/refonte/impact/a-parametres.md.
REGISTRY = [
    ("parametres", _settings_view),
    ("parametres-recherche", _settings_view_recherche),
    ("parametres-arriere-plan", _settings_view_arriere_plan),
    ("parametres-refus", _settings_view_refus),
    ("parametres-notifications", _settings_view_notifications_hebdomadaire),
    ("parametres-enregistre", _settings_view_enregistre),
    ("ressources", _resources_view),
    ("aujourdhui", _dashboard_view),
]


def _init_disposable_db():
    """Base SQLite jetable dans un dossier temporaire — jamais la vraie base applicative (même
    règle que tests/conftest.py::test_db)."""
    db_path = Path(tempfile.mkdtemp(prefix="kulu_capture_")) / "capture.db"
    db.init_db(db_path)


def capture_all(out_dir: Path) -> list[Path]:
    """Suppose qu'une base (jetable ou non) est déjà initialisée via db.init_db() — jamais
    appelé ici, pour rester réutilisable depuis un test qui a déjà sa propre base jetable
    (fixture test_db)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    register_app_fonts()
    app.setStyleSheet(GLOBAL_STYLE)

    produced = []
    for name, build_view in REGISTRY:
        view = build_view()
        view.resize(CAPTURE_WIDTH, CAPTURE_HEIGHT)
        view.show()
        app.processEvents()
        # show() sur une fenêtre top-level sans parent donne le focus clavier au premier widget
        # focusable (le champ de recherche, premier ajouté au rail) dès que rien d'autre ne l'a
        # déjà pris — un artefact du script, pas l'état par défaut réel (dans l'app, la vue est
        # intégrée à une fenêtre déjà active, ce changement de focus n'a pas lieu). Sans ce
        # nettoyage, la capture montrait à tort une bordure de focus (accent) sur le champ de
        # recherche même sur les états qui ne simulent aucune saisie utilisateur. Seule la
        # capture "recherche" doit garder ce focus (une recherche en cours a le curseur dedans,
        # Parametres-recherche.html).
        search_box = getattr(view, "inp_search", None)
        if search_box is not None and name != "parametres-recherche":
            search_box.clearFocus()
            app.processEvents()
        out_path = out_dir / f"{name}.png"
        view.grab().save(str(out_path))
        produced.append(out_path)
    return produced


if __name__ == "__main__":
    _init_disposable_db()
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "refonte" / "captures"
    for path in capture_all(out_dir):
        print(path)
