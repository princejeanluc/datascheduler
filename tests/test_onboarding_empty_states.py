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
