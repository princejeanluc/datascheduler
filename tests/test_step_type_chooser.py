"""
DataScheduler — tests/test_step_type_chooser.py
Vérifie que StepTypeChooserDialog reste utilisable avec un grand nombre de types : recherche en
direct, regroupement par catégorie, `include_routing_nodes` toujours respecté. isHidden() est utilisé
plutôt que isVisible() : ce dernier dépend aussi de la visibilité des parents et n'est donc fiable
qu'une fois le dialogue réellement affiché (exec()/show()), ce que ce test évite.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from ui.step_editor.step_type_chooser_dialog import StepTypeChooserDialog
from ui.step_editor.common import STEP_META


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_condition_hidden_from_linear_editor(qapp):
    dlg = StepTypeChooserDialog(None, include_routing_nodes=False)
    assert "CONDITION" not in dlg._visible_types()
    assert len(dlg._cards) == len(dlg._visible_types())


def test_condition_available_from_graph_editor(qapp):
    dlg = StepTypeChooserDialog(None, include_routing_nodes=True)
    assert "CONDITION" in dlg._visible_types()


def test_gateway_parallel_hidden_from_linear_editor(qapp):
    dlg = StepTypeChooserDialog(None, include_routing_nodes=False)
    assert "GATEWAY_PARALLEL" not in dlg._visible_types()


def test_gateway_parallel_available_from_graph_editor(qapp):
    dlg = StepTypeChooserDialog(None, include_routing_nodes=True)
    assert "GATEWAY_PARALLEL" in dlg._visible_types()


def test_gateway_join_hidden_from_linear_editor(qapp):
    dlg = StepTypeChooserDialog(None, include_routing_nodes=False)
    assert "GATEWAY_JOIN" not in dlg._visible_types()


def test_gateway_join_available_from_graph_editor(qapp):
    dlg = StepTypeChooserDialog(None, include_routing_nodes=True)
    assert "GATEWAY_JOIN" in dlg._visible_types()


def test_every_step_meta_entry_has_a_known_category(qapp):
    from ui.step_editor.step_type_chooser_dialog import _CATEGORY_ORDER
    for step_type, meta in STEP_META.items():
        assert meta["category"] in _CATEGORY_ORDER, step_type


def test_every_step_meta_entry_has_a_distinct_icon(qapp):
    """Chaque type d'étape doit être reconnaissable visuellement (chantier identité, vague 1,
    idée 15) — un nom d'icône qtawesome non vide, distinct même entre types proches (ex :
    DB_EXTRACT vs DB_LOAD vs DB_EXECUTE)."""
    icons = {step_type: meta["icon"] for step_type, meta in STEP_META.items()}
    for step_type, icon in icons.items():
        assert isinstance(icon, str) and icon, step_type
    assert len(set(icons.values())) == len(icons), "deux types partagent la même icône"


def test_all_cards_present_by_default(qapp):
    dlg = StepTypeChooserDialog(None, include_routing_nodes=True)
    assert len(dlg._cards) == len(dlg._visible_types())
    assert all(not card.isHidden() for card, _ in dlg._cards)
    assert all(not header.isHidden() for header, _ in dlg._category_sections.values())


def test_search_filters_cards_and_collapses_empty_categories(qapp):
    dlg = StepTypeChooserDialog(None, include_routing_nodes=True)

    dlg.inp_search.setText("ftp")
    visible = [card for card, text in dlg._cards if not card.isHidden()]
    assert len(visible) == 2   # FTP_UPLOAD (Transfert & diffusion) + FTP_DOWNLOAD (Extraction & chargement)

    visible_headers = [h for h, frames in dlg._category_sections.values() if not h.isHidden()]
    assert len(visible_headers) == 2

    dlg.inp_search.setText("aucune correspondance possible")
    assert all(card.isHidden() for card, _ in dlg._cards)
    assert all(header.isHidden() for header, _ in dlg._category_sections.values())

    dlg.inp_search.setText("")
    assert all(not card.isHidden() for card, _ in dlg._cards)


def test_search_matches_category_name(qapp):
    dlg = StepTypeChooserDialog(None, include_routing_nodes=True)
    dlg.inp_search.setText("contrôle de flux")
    visible = [card for card, _ in dlg._cards if not card.isHidden()]
    # CONDITION + GATEWAY_PARALLEL + GATEWAY_JOIN (chantier Gateway) partagent cette catégorie.
    assert len(visible) == 3


def test_choosing_a_filtered_card_returns_correct_step_type(qapp):
    dlg = StepTypeChooserDialog(None, include_routing_nodes=True)
    dlg.inp_search.setText("condition")
    dlg._choose("CONDITION")
    assert dlg.chosen_type == "CONDITION"
