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


def test_every_registered_step_type_has_a_chooser_description(qapp):
    """Régression réelle (v0.34.0/v0.35.0) : SQOOP_IMPORT puis EXTRACT_VARIABLES ont été
    enregistrés dans STEP_META/le registre de steps mais jamais ajoutés à _DESCRIPTIONS —
    _DESCRIPTIONS pilote seul le dialogue "Ajouter une étape" (_visible_types() itère dessus,
    jamais sur STEP_META), donc les deux sont restés invisibles à l'ajout malgré des dialogues de
    configuration et une exécution parfaitement fonctionnels. Ce test échoue dès qu'un futur type
    d'étape est enregistré sans mise à jour de _DESCRIPTIONS, plutôt que de dépendre d'un
    utilisateur pour le remarquer."""
    from ui.step_editor.step_type_chooser_dialog import _DESCRIPTIONS
    missing = set(STEP_META) - set(_DESCRIPTIONS)
    assert not missing, f"types absents de _DESCRIPTIONS (invisibles dans « Ajouter une étape ») : {missing}"


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
    # CONDITION + GATEWAY_PARALLEL + GATEWAY_JOIN (chantier Gateway) + EXTRACT_VARIABLES
    # (chantier EXTRACT_VARIABLES) + SET_VARIABLE (chantier SET_VARIABLE) partagent cette
    # catégorie.
    assert len(visible) == 5


def test_choosing_a_filtered_card_returns_correct_step_type(qapp):
    dlg = StepTypeChooserDialog(None, include_routing_nodes=True)
    dlg.inp_search.setText("condition")
    dlg._choose("CONDITION")
    assert dlg.chosen_type == "CONDITION"


# ──────────────────────────────────────────────
#  Chantier bibliothèque d'étapes réutilisables — section "Mes modèles"
# ──────────────────────────────────────────────

import json
from PySide6.QtWidgets import QInputDialog, QMessageBox
from database import db_manager as db


def test_no_templates_section_when_no_templates_exist(qapp, test_db):
    dlg = StepTypeChooserDialog(None, include_routing_nodes=True)
    assert "Mes modèles" not in dlg._category_sections
    assert dlg._templates_layout.count() == 0


def test_templates_section_lists_existing_templates(qapp, test_db):
    db.create_step_template(name="Dépôt partenaire", step_type="FTP_UPLOAD",
                             config={"ftp_profile_id": 1})
    dlg = StepTypeChooserDialog(None, include_routing_nodes=True)
    assert "Mes modèles" in dlg._category_sections
    header, frames = dlg._category_sections["Mes modèles"]
    assert len(frames) == 1
    assert not header.isHidden()


def test_templates_with_unknown_step_type_are_silently_excluded(qapp, test_db):
    db.create_step_template(name="Modèle obsolète", step_type="TYPE_INEXISTANT_XYZ", config={})
    dlg = StepTypeChooserDialog(None, include_routing_nodes=True)
    assert "Mes modèles" not in dlg._category_sections   # exclu, aucune erreur levée


def test_choosing_a_template_card_sets_chosen_type_and_config(qapp, test_db):
    template = db.create_step_template(
        name="Dépôt partenaire", step_type="FTP_UPLOAD",
        config={"ftp_profile_id": 1, "remote_path_tpl": "/export/"},
    )
    dlg = StepTypeChooserDialog(None, include_routing_nodes=True)

    dlg._choose_template(template)

    assert dlg.chosen_type == "FTP_UPLOAD"
    assert dlg.chosen_config == {"ftp_profile_id": 1, "remote_path_tpl": "/export/"}


def test_template_search_matches_its_own_name(qapp, test_db):
    db.create_step_template(name="Dépôt partenaire spécial", step_type="FTP_UPLOAD", config={})
    dlg = StepTypeChooserDialog(None, include_routing_nodes=True)

    dlg.inp_search.setText("spécial")

    header, frames = dlg._category_sections["Mes modèles"]
    assert not frames[0].isHidden()
    assert not header.isHidden()


def test_template_search_does_not_match_unrelated_text(qapp, test_db):
    db.create_step_template(name="Dépôt partenaire", step_type="FTP_UPLOAD", config={})
    dlg = StepTypeChooserDialog(None, include_routing_nodes=True)

    dlg.inp_search.setText("aucune correspondance possible")

    header, frames = dlg._category_sections["Mes modèles"]
    assert frames[0].isHidden()
    assert header.isHidden()


def test_rename_template_via_inline_button(qapp, test_db, monkeypatch):
    template = db.create_step_template(name="Ancien nom", step_type="FTP_UPLOAD", config={})
    dlg = StepTypeChooserDialog(None, include_routing_nodes=True)

    monkeypatch.setattr(QInputDialog, "getText",
                         staticmethod(lambda *a, **k: ("Nouveau nom", True)))
    dlg._on_rename_template(template.id, "Ancien nom")

    assert db.get_step_template(template.id).name == "Nouveau nom"
    header, frames = dlg._category_sections["Mes modèles"]
    assert len(frames) == 1   # section reconstruite, toujours un seul modèle


def test_rename_template_cancelled_prompt_keeps_old_name(qapp, test_db, monkeypatch):
    template = db.create_step_template(name="Ancien nom", step_type="FTP_UPLOAD", config={})
    dlg = StepTypeChooserDialog(None, include_routing_nodes=True)

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))
    dlg._on_rename_template(template.id, "Ancien nom")

    assert db.get_step_template(template.id).name == "Ancien nom"


def test_delete_template_via_inline_button_after_confirmation(qapp, test_db, monkeypatch):
    template = db.create_step_template(name="M", step_type="FTP_UPLOAD", config={})
    dlg = StepTypeChooserDialog(None, include_routing_nodes=True)

    monkeypatch.setattr(QMessageBox, "question",
                         staticmethod(lambda *a, **k: QMessageBox.Yes))
    dlg._on_delete_template(template.id, "M")

    assert db.get_step_template(template.id) is None
    assert "Mes modèles" not in dlg._category_sections


def test_delete_template_without_confirmation_keeps_it(qapp, test_db, monkeypatch):
    template = db.create_step_template(name="M", step_type="FTP_UPLOAD", config={})
    dlg = StepTypeChooserDialog(None, include_routing_nodes=True)

    monkeypatch.setattr(QMessageBox, "question",
                         staticmethod(lambda *a, **k: QMessageBox.No))
    dlg._on_delete_template(template.id, "M")

    assert db.get_step_template(template.id) is not None
