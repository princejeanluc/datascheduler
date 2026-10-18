"""
DataScheduler — tests/test_ftp_dialog_remote_dir_removed.py
Correctif K4 (docs/refonte/LOTS.md) : le champ "Dossier distant" de FtpDialog n'était ni
enregistré ni relu (FtpProfile n'a aucune colonne pour cette donnée) — retiré du formulaire
plutôt que câblé, pour ne pas changer le format d'export (décision prise dans LOTS.md).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_ftp_dialog_has_no_remote_dir_field(qapp):
    from ui.dialogs.ftp_dialog import FtpDialog

    dlg = FtpDialog()
    assert not hasattr(dlg, "inp_remote_dir")


def test_ftp_dialog_still_saves_and_reloads_without_it(qapp, test_db):
    """Non-régression : le reste du formulaire continue de fonctionner normalement."""
    from ui.dialogs.ftp_dialog import FtpDialog
    from database import db_manager as db

    dlg = FtpDialog()
    dlg.inp_name.setText("FTP_TEST")
    dlg.inp_host.setText("ftp.example.com")
    dlg.inp_user.setText("user1")
    dlg.inp_pass.setText("secret")
    dlg._on_save()

    profiles = db.get_ftp_profiles()
    assert len(profiles) == 1
    assert profiles[0].name == "FTP_TEST"
    assert profiles[0].host == "ftp.example.com"
