"""
DataScheduler — tests/test_onboarding_empty_states.py
Fumée (offscreen Qt) : messages d'état vide pédagogiques (chantier UX ergonomie, E.7) — le
parcours utilisateur ne s'expliquait nulle part (Connexions → Requêtes SQL → Pipelines). Les
messages d'état vide enseignent désormais cet ordre, et le Dashboard affiche une bannière
d'accueil tant qu'aucun pipeline n'existe.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_dashboard_shows_onboarding_banner_when_no_pipelines(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    view = DashboardView()
    assert not view._onboarding_banner.isHidden()


def test_dashboard_hides_onboarding_banner_once_a_pipeline_exists(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    db.create_pipeline(name="onboarding-test-pipeline")
    view = DashboardView()
    assert view._onboarding_banner.isHidden()


# ── A12 : accueil "premier pipeline" (trois cartes + deux liens) ───────────

def test_onboarding_banner_shows_three_cards_and_two_links(qapp, test_db):
    from PySide6.QtWidgets import QPushButton
    from ui.main_window.dashboard_view import DashboardView

    view = DashboardView()
    buttons = [b.text().strip() for b in view._onboarding_banner.findChildren(QPushButton)]
    assert "Créer une connexion" in buttons
    assert "Ouvrir l'éditeur SQL" in buttons
    assert "Partir du modèle" in buttons
    assert "Importer un fichier .dspipeline" in buttons
    assert "Lire le guide pas à pas" in buttons


@pytest.mark.parametrize("button_text, signal_name", [
    ("Créer une connexion", "open_connections_requested"),
    ("Ouvrir l'éditeur SQL", "open_sql_editor_requested"),
    ("Partir du modèle", "start_from_template_requested"),
    ("Importer un fichier .dspipeline", "import_pipeline_requested"),
    ("Lire le guide pas à pas", "open_help_requested"),
])
def test_onboarding_banner_button_emits_its_signal(qapp, test_db, button_text, signal_name):
    from PySide6.QtWidgets import QPushButton
    from ui.main_window.dashboard_view import DashboardView

    view = DashboardView()
    received = []
    getattr(view, signal_name).connect(lambda *a: received.append(True))

    btn = next(
        b for b in view._onboarding_banner.findChildren(QPushButton)
        if b.text().strip() == button_text
    )
    btn.click()

    assert received == [True]


def test_onboarding_card_style_is_id_scoped_not_a_bare_rule(qapp, test_db):
    """Régression : même classe de bug que les cartes "À traiter" et la ligne de rattrapage
    (QLabel hérite de QFrame en Qt, REGLES.md section 3) — vérifié ici par précaution."""
    from PySide6.QtWidgets import QFrame
    from ui.main_window.dashboard_view import DashboardView

    view = DashboardView()
    card = view._onboarding_banner.findChild(QFrame, "onboarding_card_1")
    assert card is not None
    assert "QFrame#onboarding_card_1" in card.styleSheet()


def test_pipelines_empty_state_mentions_connections_and_queries(qapp, test_db):
    """_empty_label est désormais un conteneur composite (label + bouton "Commencer avec un
    modèle", chantier UX éditeur Lot 1/C1), plus un QLabel nu — le texte pédagogique vit dans
    son QLabel enfant."""
    from ui.main_window.pipelines_view import PipelinesView

    view = PipelinesView()
    text = view._empty_label.findChild(QLabel).text()
    assert "Connexions" in text
    assert "Requêtes SQL" in text


def test_pipelines_empty_state_has_start_from_template_button(qapp, test_db):
    from PySide6.QtWidgets import QPushButton
    from ui.main_window.pipelines_view import PipelinesView

    view = PipelinesView()
    buttons = [b.text().strip() for b in view._empty_label.findChildren(QPushButton)]
    assert any("modèle" in b.lower() for b in buttons)


def test_queries_empty_state_mentions_step_types(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    view = QueriesView()
    text = view._empty_label.text()
    assert "DB_EXTRACT" in text
    assert "Spark SQL" in text
