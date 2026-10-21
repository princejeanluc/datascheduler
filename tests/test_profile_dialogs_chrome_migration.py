"""
DataScheduler — tests/test_profile_dialogs_chrome_migration.py
Refonte, lot A-Connexions (A8/A9) : migration des 7 dialogues de profil vers le chrome partagé
(ui/dialogs/_profile_dialog_chrome.py) — un test de fumée par dialogue (aucun test UI dédié
n'existait avant ce lot pour Oracle/Database/Ftp/Smtp ; SSH/Kerberos/Élévation sont couverts plus
en détail par test_ssh_kerberos_ui.py, revérifié séparément)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _texts(widget) -> list:
    return [lbl.text() for lbl in widget.findChildren(QLabel) if lbl.text()]


def test_oracle_dialog_header_and_banner(qapp, test_db):
    from ui.dialogs import OracleDialog

    created = OracleDialog()
    assert "NOUVEAU · BASES DE DONNÉES" in _texts(created)

    p = db.create_oracle_profile(name="ORA-CHROME", host="h", port=1521, service_name="s",
                                  username="u", password="pw")
    edited = OracleDialog(profile=p)
    assert "MODIFIER · BASES DE DONNÉES" in _texts(edited)
    assert "ORA-CHROME" in _texts(edited)

    edited._on_test_result(True, "", "19c")
    texts = _texts(edited)
    assert any("Connexion réussie à" in t for t in texts)
    assert "Oracle 19c" in texts

    edited._on_test_result(False, "ORA-12541: TNS:no listener", "")
    texts = _texts(edited)
    assert any("Le test a échoué à" in t for t in texts)
    assert "ORA-12541: TNS:no listener" in texts


def test_database_profile_dialog_header_and_banner(qapp, test_db):
    from ui.dialogs import DatabaseProfileDialog

    created = DatabaseProfileDialog(db_type="POSTGRESQL")
    assert "NOUVEAU · BASES DE DONNÉES" in _texts(created)

    created._on_test_result(False, "connection refused")
    assert "connection refused" in _texts(created)


def test_ftp_dialog_header_and_banner(qapp, test_db):
    from ui.dialogs import FtpDialog

    p = db.create_ftp_profile(name="SFTP Partenaire", host="h", port=22,
                               username="u", password="pw", protocol="SFTP")
    dlg = FtpDialog(profile=p)
    assert "MODIFIER · FICHIERS" in _texts(dlg)
    assert "SFTP Partenaire" in _texts(dlg)

    dlg._on_test_result(True, "dossier /depot/in accessible")
    assert "dossier /depot/in accessible" in _texts(dlg)


def test_smtp_dialog_header_and_banner(qapp, test_db):
    from ui.dialogs import SmtpDialog

    dlg = SmtpDialog()
    assert "NOUVEAU · E-MAIL" in _texts(dlg)

    dlg._on_test_result(True, "connexion ouverte en 0,2 s")
    assert "connexion ouverte en 0,2 s" in _texts(dlg)


def test_ssh_dialog_header(qapp, test_db):
    from ui.dialogs import SshProfileDialog

    dlg = SshProfileDialog()
    assert "NOUVEAU · BIG DATA" in _texts(dlg)


def test_kerberos_dialog_header_ssh_picker_and_banner(qapp, test_db):
    from ui.dialogs import KerberosProfileDialog

    dlg = KerberosProfileDialog()
    assert "NOUVEAU · BIG DATA" in _texts(dlg)
    assert "Profil SSH pour le test" in _texts(dlg)
    assert dlg.btn_test.text() == "⚡  Tester (kinit)"

    dlg._on_test_result(True, "ticket obtenu (kinit)")
    assert any("Connexion réussie à" in t for t in _texts(dlg))
    assert "ticket obtenu (kinit)" in _texts(dlg)


def test_elevation_dialog_header_ssh_picker_and_banner(qapp, test_db):
    from ui.dialogs import ElevationProfileDialog

    dlg = ElevationProfileDialog()
    assert "NOUVEAU · BIG DATA" in _texts(dlg)
    assert "Profil SSH pour le test" in _texts(dlg)
    assert dlg.btn_test.text() == "⚡  Tester (sudo su)"

    dlg._on_test_result(False, "Permission denied")
    assert any("Le test a échoué à" in t for t in _texts(dlg))
    assert "Permission denied" in _texts(dlg)


def test_footer_note_is_present_on_every_profile_dialog(qapp, test_db):
    """A9 : « Le test utilise les valeurs saisies, pas celles enregistrées. » sur les 7
    dialogues."""
    from ui.dialogs import (
        OracleDialog, DatabaseProfileDialog, FtpDialog, SmtpDialog, SshProfileDialog,
        KerberosProfileDialog, ElevationProfileDialog,
    )

    note = "Le test utilise les valeurs saisies, pas celles enregistrées."
    for dlg in (
        OracleDialog(), DatabaseProfileDialog(db_type="MYSQL"), FtpDialog(), SmtpDialog(),
        SshProfileDialog(), KerberosProfileDialog(), ElevationProfileDialog(),
    ):
        assert note in _texts(dlg)
