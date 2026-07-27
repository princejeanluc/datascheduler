"""
DataScheduler — tests/test_step_type_chooser.py
Vérifie que StepTypeChooserDialog reste utilisable avec un grand nombre de types : recherche en
direct, regroupement par catégorie, `include_condition` toujours respecté. isHidden() est utilisé
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
    dlg = StepTypeChooserDialog(None, include_condition=False)
    assert "CONDITION" not in dlg._visible_types()
    assert len(dlg._cards) == len(dlg._visible_types())


def test_condition_available_from_graph_editor(qapp):
    dlg = StepTypeChooserDialog(None, include_condition=True)
    assert "CONDITION" in dlg._visible_types()


def test_every_step_meta_entry_has_a_known_category(qapp):
    from ui.step_editor.step_type_chooser_dialog import _CATEGORY_ORDER
    for step_type, meta in STEP_META.items():
        assert meta["category"] in _CATEGORY_ORDER, step_type


def test_all_cards_present_by_default(qapp):
    dlg = StepTypeChooserDialog(None, include_condition=True)
    assert len(dlg._cards) == len(dlg._visible_types())
    assert all(not card.isHidden() for card, _ in dlg._cards)
    assert all(not header.isHidden() for header, _ in dlg._category_sections.values())


def test_search_filters_cards_and_collapses_empty_categories(qapp):
    dlg = StepTypeChooserDialog(None, include_condition=True)

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
    dlg = StepTypeChooserDialog(None, include_condition=True)
    dlg.inp_search.setText("contrôle de flux")
    visible = [card for card, _ in dlg._cards if not card.isHidden()]
    assert len(visible) == 1   # seul CONDITION est dans cette catégorie


def test_choosing_a_filtered_card_returns_correct_step_type(qapp):
    dlg = StepTypeChooserDialog(None, include_condition=True)
    dlg.inp_search.setText("condition")
    dlg._choose("CONDITION")
    assert dlg.chosen_type == "CONDITION"
