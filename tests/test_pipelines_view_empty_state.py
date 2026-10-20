"""
DataScheduler — tests/test_pipelines_view_empty_state.py
Refonte, lot A-Pipelines : A14 (état vide en trois cartes).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_empty_state_shows_three_cards_and_their_buttons(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    view = PipelinesView()
    labels = [lbl.text() for lbl in view._empty_label.findChildren(QLabel)]
    buttons = [b.text() for b in view._empty_label.findChildren(QPushButton)]

    assert "Partir du modèle" in labels
    assert "Toile vierge" in labels
    assert "Importer un .dspipeline" in labels
    assert "Commencer avec un modèle" in buttons
    assert "Nouveau pipeline" in buttons
    assert "Importer" in buttons


def test_empty_state_card_buttons_trigger_their_callback(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    view = PipelinesView()
    calls = []
    monkeypatch.setattr(view, "_on_start_from_template", lambda: calls.append("template"))
    monkeypatch.setattr(view, "_on_new_pipeline", lambda: calls.append("new"))
    monkeypatch.setattr(view, "_on_import_pipeline", lambda: calls.append("import"))

    # Reconstruire l'état vide après le monkeypatch (les boutons sont câblés à la construction).
    view._empty_label = view._build_pipelines_empty_state()
    buttons = {b.text(): b for b in view._empty_label.findChildren(QPushButton)}
    buttons["Commencer avec un modèle"].click()
    buttons["Nouveau pipeline"].click()
    buttons["Importer"].click()

    assert calls == ["template", "new", "import"]


def test_empty_state_card_style_is_id_scoped_not_a_bare_rule(qapp, test_db):
    """Régression : même classe de bug que les cartes d'accueil d'Aujourd'hui (QLabel hérite de
    QFrame en Qt, REGLES.md section 3)."""
    from PySide6.QtWidgets import QFrame
    from ui.main_window.pipelines_view import PipelinesView

    view = PipelinesView()
    card = view._empty_label.findChild(QFrame, "empty_card_Partir_du_modèle")
    assert card is not None
    assert "QFrame#empty_card_Partir_du_modèle" in card.styleSheet()
