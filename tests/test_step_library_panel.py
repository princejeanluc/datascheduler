"""
DataScheduler — tests/test_step_library_panel.py
StepLibraryPanel (C7, Atelier-ajout) : recherche, Mes modèles (renommer/supprimer repris,
voir docs/refonte/impact/c7-atelier-ajout.md — seul appelant de StepTypeChooserDialog en
production changeant de comportement), Passerelles, catégories, sélection au clic.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from ui.graph_editor.step_library_panel import StepLibraryPanel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_constructs_without_raising_and_lists_every_non_routing_type(qapp, test_db):
    panel = StepLibraryPanel()
    types = {c._step_type for c in panel._cards}
    assert "LOCAL_COPY" in types
    assert "CONDITION" in types   # via le badge Passerelles, pas une carte normale


def test_clicking_a_card_selects_it_and_emits_selection_changed(qapp, test_db):
    panel = StepLibraryPanel()
    received = []
    panel.selection_changed.connect(lambda t, c: received.append((t, c)))

    card = next(c for c in panel._cards if c._step_type == "LOCAL_COPY")
    card.clicked.emit()

    assert received == [("LOCAL_COPY", {})]
    assert panel._selected_type == "LOCAL_COPY"
    assert card._selected is True


def test_selecting_a_different_card_deselects_the_previous_one(qapp, test_db):
    panel = StepLibraryPanel()
    card_a = next(c for c in panel._cards if c._step_type == "LOCAL_COPY")
    card_b = next(c for c in panel._cards if c._step_type == "COMPRESS")

    card_a.clicked.emit()
    card_b.clicked.emit()

    assert card_a._selected is False
    assert card_b._selected is True


def test_search_hides_non_matching_cards_and_their_empty_section_headers(qapp, test_db):
    panel = StepLibraryPanel()
    panel._on_search_changed("oracle")

    visible_types = {c._step_type for c in panel._cards if not c.isHidden()}
    assert visible_types == {"DB_EXTRACT", "SQOOP_EXPORT", "SQOOP_IMPORT"}

    # Une section sans aucune carte visible doit masquer son en-tête (ex: PASSERELLES, aucun
    # badge ne correspond à "oracle").
    for header, cards in panel._sections:
        if not any(not c.isHidden() for c in cards):
            assert header.isHidden()


def test_clearing_the_search_shows_every_card_again(qapp, test_db):
    panel = StepLibraryPanel()
    panel._on_search_changed("oracle")
    panel._on_search_changed("")
    assert all(not c.isHidden() for c in panel._cards)


def test_return_without_a_selection_auto_selects_the_first_visible_match(qapp, test_db):
    panel = StepLibraryPanel()
    received = []
    panel.insert_requested.connect(lambda: received.append(True))
    panel._on_search_changed("copie")

    panel._on_return_pressed()

    assert panel._selected_type == "LOCAL_COPY"
    assert received == [True]


def test_return_with_no_visible_card_is_a_no_op(qapp, test_db):
    panel = StepLibraryPanel()
    received = []
    panel.insert_requested.connect(lambda: received.append(True))
    panel._on_search_changed("ceci ne correspond à rien du tout")

    panel._on_return_pressed()

    assert received == []


def test_mes_modeles_section_lists_a_saved_template_and_prefills_its_config(qapp, test_db):
    from database import db_manager as db

    db.create_step_template("Dépôt SFTP partenaire", "FTP_UPLOAD", {"remote_path_tpl": "/in/"})

    panel = StepLibraryPanel()
    received = []
    panel.selection_changed.connect(lambda t, c: received.append((t, c)))

    template_card = next(c for c in panel._cards if getattr(c, "_is_template_card", False))
    assert template_card._step_type == "FTP_UPLOAD"
    template_card.clicked.emit()

    assert received == [("FTP_UPLOAD", {"remote_path_tpl": "/in/"})]


def test_deleting_a_template_removes_it_from_the_panel(qapp, test_db, monkeypatch):
    from database import db_manager as db
    from PySide6.QtWidgets import QMessageBox

    template = db.create_step_template("À supprimer", "LOCAL_COPY", {})
    panel = StepLibraryPanel()
    assert any(getattr(c, "_is_template_card", False) for c in panel._cards)

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    panel._on_delete_template(template.id, template.name)

    assert not any(getattr(c, "_is_template_card", False) for c in panel._cards)
    assert db.get_step_templates() == []


def test_no_templates_means_no_mes_modeles_section_at_all(qapp, test_db):
    panel = StepLibraryPanel()
    assert not any(getattr(c, "_is_template_card", False) for c in panel._cards)
    assert panel._templates_header is None
