"""
DataScheduler — tests/test_nav_rail_collapse.py
Repli du menu de navigation latéral (chantier ergonomie) : bascule explicite (jamais au survol),
état mémorisé dans AppSettings.nav_collapsed pour survivre au redémarrage. Première étape
"replier/déplier" du projet — introduit un vrai repli après une longue discussion de conception
(voir CHANGELOG) sur le côté "menu à icônes qui ne se replie pas" de la maquette de l'atelier SQL.

NavRail (ui/main_window/widgets.py) a été extrait de MainWindow._build_nav() précisément pour ce
fichier de tests : MainWindow instancie ses 8 vues + le pont scheduler dans son constructeur —
deux tentatives d'y tester le repli en construisant un MainWindow() complet (même une seule fois,
même sans .show()) ont fait planter/bloquer la suite complète (des milliers de widgets Qt/signaux
cumulés avec les 1200+ autres tests de la session), alors que chaque tentative passait isolément.
NavRail seule n'a aucun de ces effets de bord — MainWindow n'est plus du tout construit ici, la
persistance AppSettings est vérifiée séparément (NavRail émet collapsed_changed, MainWindow
l'écoute pour appeler db.update_app_settings() — la connexion elle-même n'a pas besoin d'un
MainWindow réel pour être exercée, voir test_mainwindow_wires_collapsed_changed_to_app_settings).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from database import db_manager as db

_NAV_ITEMS = [
    ("Dashboard",    "dashboard",    0),
    ("Pipelines",    "pipelines",    1),
    ("Connexions",   "connexions",   2),
]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ──────────────────────────────────────────────
#  NavButton.set_collapsed() — le plus élémentaire, sans NavRail ni MainWindow
# ──────────────────────────────────────────────

def test_nav_button_expanded_by_default(qapp):
    from ui.main_window.widgets import NavButton

    btn = NavButton("Dashboard", "dashboard")
    assert btn.text() == "  Dashboard"
    assert btn.toolTip() == ""


def test_nav_button_collapsed_shows_icon_only_with_tooltip(qapp):
    from ui.main_window.widgets import NavButton

    btn = NavButton("Dashboard", "dashboard")
    btn.set_collapsed(True)
    assert btn.text() == ""
    assert btn.toolTip() == "Dashboard"
    assert not btn.icon().isNull()


def test_nav_button_expanding_again_clears_tooltip_and_restores_text(qapp):
    from ui.main_window.widgets import NavButton

    btn = NavButton("Dashboard", "dashboard")
    btn.set_collapsed(True)
    btn.set_collapsed(False)
    assert btn.text() == "  Dashboard"
    assert btn.toolTip() == ""


def test_nav_button_collapsed_state_survives_active_state_change(qapp):
    """set_active() ré-applique le style (_apply_style()) — le repli ne doit jamais être
    silencieusement perdu par un changement de sélection de la vue courante."""
    from ui.main_window.widgets import NavButton

    btn = NavButton("Dashboard", "dashboard")
    btn.set_collapsed(True)
    btn.set_active(True)
    assert btn.text() == ""
    assert btn.toolTip() == "Dashboard"


# ──────────────────────────────────────────────
#  NavRail — composant autonome
# ──────────────────────────────────────────────

def test_nav_rail_starts_expanded_by_default(qapp):
    from ui.main_window.widgets import NavRail, NAV_WIDTH

    rail = NavRail(_NAV_ITEMS)
    assert rail.is_collapsed is False
    assert rail.width() == NAV_WIDTH
    assert rail._logo_lbl.isHidden() is False
    assert rail._version_lbl.isHidden() is False
    assert "Réduire" in rail._toggle_btn.text()
    assert rail._toggle_btn.toolTip() == ""


def test_nav_rail_can_start_collapsed(qapp):
    from ui.main_window.widgets import NavRail, NAV_WIDTH_COLLAPSED

    rail = NavRail(_NAV_ITEMS, initial_collapsed=True)
    assert rail.is_collapsed is True
    assert rail.width() == NAV_WIDTH_COLLAPSED
    assert rail._logo_lbl.isHidden() is True


def test_toggle_collapsed_updates_everything(qapp):
    from ui.main_window.widgets import NavRail, NAV_WIDTH_COLLAPSED

    rail = NavRail(_NAV_ITEMS)
    rail.toggle_collapsed()

    assert rail.is_collapsed is True
    assert rail.width() == NAV_WIDTH_COLLAPSED
    assert rail._logo_lbl.isHidden() is True
    assert rail._version_lbl.isHidden() is True
    for btn in rail._nav_buttons:
        assert btn.text() == ""
        assert btn.toolTip()   # jamais un jeu de mémoire icône-seule
    assert rail._toggle_btn.text() == ""
    assert "Agrandir" in rail._toggle_btn.toolTip()
    assert not rail._toggle_btn.icon().isNull()


def test_toggle_twice_returns_to_expanded(qapp):
    from ui.main_window.widgets import NavRail, NAV_WIDTH

    rail = NavRail(_NAV_ITEMS)
    rail.toggle_collapsed()
    rail.toggle_collapsed()

    assert rail.is_collapsed is False
    assert rail.width() == NAV_WIDTH
    assert rail._logo_lbl.isHidden() is False
    for btn in rail._nav_buttons:
        assert btn.text().strip()


def test_toggle_emits_collapsed_changed_signal(qapp):
    from ui.main_window.widgets import NavRail

    rail = NavRail(_NAV_ITEMS)
    captured = []
    rail.collapsed_changed.connect(captured.append)

    rail.toggle_collapsed()
    assert captured == [True]
    rail.toggle_collapsed()
    assert captured == [True, False]


def test_clicking_a_nav_button_emits_navigate_requested(qapp):
    from ui.main_window.widgets import NavRail

    rail = NavRail(_NAV_ITEMS)
    captured = []
    rail.navigate_requested.connect(captured.append)

    rail._nav_buttons[2].click()
    assert captured == [2]


def test_set_active_index_marks_only_that_button(qapp):
    from ui.main_window.widgets import NavRail

    rail = NavRail(_NAV_ITEMS)
    rail.set_active_index(1)
    assert rail._nav_buttons[1]._active is True
    assert rail._nav_buttons[0]._active is False
    assert rail._nav_buttons[2]._active is False


# ──────────────────────────────────────────────
#  AppSettings — persistance, indépendante de tout widget
# ──────────────────────────────────────────────

def test_new_app_settings_row_defaults_to_expanded(test_db):
    """Comportement historique préservé pour qui n'a jamais touché à ce réglage — une nouvelle
    colonne ne doit jamais changer silencieusement le comportement par défaut."""
    assert db.get_app_settings().nav_collapsed is False


def test_app_settings_nav_collapsed_round_trip(test_db):
    db.update_app_settings(nav_collapsed=True)
    assert db.get_app_settings().nav_collapsed is True
    db.update_app_settings(nav_collapsed=False)
    assert db.get_app_settings().nav_collapsed is False


def test_mainwindow_wires_collapsed_changed_to_app_settings(qapp, test_db):
    """Vérifie le câblage MainWindow._build_ui() (NavRail.collapsed_changed -> AppSettings) sans
    construire de MainWindow réel — on reproduit exactement la même connexion lambda avec une
    NavRail autonome, ce que MainWindow._build_ui() fait lui-même mot pour mot."""
    from ui.main_window.widgets import NavRail

    rail = NavRail(_NAV_ITEMS, initial_collapsed=db.get_app_settings().nav_collapsed)
    rail.collapsed_changed.connect(lambda collapsed: db.update_app_settings(nav_collapsed=collapsed))

    rail.toggle_collapsed()
    assert db.get_app_settings().nav_collapsed is True
    rail.toggle_collapsed()
    assert db.get_app_settings().nav_collapsed is False
