"""
DataScheduler — tests/test_profile_dialog_chrome.py
Refonte, lot A-Connexions : chrome partagé des 7 dialogues de profil
(ui/dialogs/_profile_dialog_chrome.py) — en-tête, bandeau de résultat de test, pied de boutons.
Testé ici sans consommateur, avant sa migration dans chaque dialogue.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_build_header_shows_eyebrow_family_and_title_create_vs_edit(qapp):
    from ui.dialogs._profile_dialog_chrome import build_header

    created = build_header("ftp", "Connexion FTP / FTPS / SFTP", editing=False)
    texts = [lbl.text() for lbl in created.findChildren(QLabel)]
    assert "NOUVEAU · FICHIERS" in texts
    assert "Connexion FTP / FTPS / SFTP" in texts

    edited = build_header("ftp", "SFTP Partenaire", editing=True)
    texts = [lbl.text() for lbl in edited.findChildren(QLabel)]
    assert "MODIFIER · FICHIERS" in texts


def test_build_header_maps_each_category_to_its_family_label(qapp):
    from ui.dialogs._profile_dialog_chrome import build_header

    expected = {
        "oracle": "BASES DE DONNÉES", "database": "BASES DE DONNÉES",
        "ftp": "FICHIERS", "smtp": "E-MAIL",
        "ssh": "BIG DATA", "kerberos": "BIG DATA", "elevation": "BIG DATA",
    }
    for category, family in expected.items():
        header = build_header(category, "Titre", editing=True)
        texts = [lbl.text() for lbl in header.findChildren(QLabel)]
        assert f"MODIFIER · {family}" in texts


def test_banner_container_starts_empty_and_rebuilds_on_each_call(qapp, test_db):
    """deleteLater() ne détruit l'ancien bandeau qu'au prochain passage de la boucle d'événements
    (même piège déjà rencontré pour HistoryView._refresh_audit_log) — processEvents() entre
    chaque appel pour vérifier l'état réellement affiché, pas un enfant pas encore nettoyé."""
    from ui.dialogs._profile_dialog_chrome import make_test_banner_container, test_result_title

    container, set_banner = make_test_banner_container()
    assert container.layout().count() == 0

    set_banner("danger", test_result_title(False), "Authentication failed")
    assert container.layout().count() == 1
    texts = [lbl.text() for lbl in container.findChildren(QLabel)]
    assert any("Le test a échoué à" in t for t in texts)
    assert "Authentication failed" in texts

    set_banner("success", test_result_title(True))
    qapp.processEvents()
    assert container.layout().count() == 1   # remplacé, pas empilé
    texts = [lbl.text() for lbl in container.findChildren(QLabel)]
    assert any("Connexion réussie à" in t for t in texts)
    assert "Authentication failed" not in texts

    set_banner(None)
    qapp.processEvents()
    assert container.layout().count() == 0
    assert container.findChildren(QLabel) == []


def test_banner_message_uses_mono_font(qapp, test_db):
    from ui.dialogs._profile_dialog_chrome import make_test_banner_container
    from ui.styles import FONT_MONO

    container, set_banner = make_test_banner_container()
    set_banner("danger", "Le test a échoué", "ORA-12541: TNS:no listener")

    message_lbl = next(
        lbl for lbl in container.findChildren(QLabel)
        if lbl.text() == "ORA-12541: TNS:no listener"
    )
    assert FONT_MONO in message_lbl.styleSheet()


def test_build_footer_wires_the_three_buttons_in_order(qapp):
    from ui.dialogs._profile_dialog_chrome import build_footer

    calls = []
    row, btn_test, btn_cancel, btn_save = build_footer(
        "⚡  Tester la connexion",
        lambda: calls.append("test"),
        lambda: calls.append("cancel"),
        lambda: calls.append("save"),
    )
    assert btn_test.text() == "⚡  Tester la connexion"
    assert btn_test.objectName() == "secondary"
    assert btn_cancel.objectName() == "secondary"

    btn_test.click(); btn_cancel.click(); btn_save.click()
    assert calls == ["test", "cancel", "save"]
