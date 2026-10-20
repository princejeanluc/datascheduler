"""
DataScheduler — tests/test_connection_delete_dialog.py
Refonte, lot A-Connexions : A11 (fenêtre de suppression modale, remplace le
`QMessageBox.question` inline de `ConnectionsView._confirm_delete`) — même patron que
`ui/dialogs/pipeline_delete_dialog.py` (lot A-Pipelines).
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


def _texts(dlg) -> list:
    return [lbl.text() for lbl in dlg.findChildren(QLabel) if lbl.text()]


def test_dialog_without_usage_shows_simple_question(qapp):
    from ui.dialogs import ConnectionDeleteDialog

    dlg = ConnectionDeleteDialog(None, "FTP", "Partage ventes", [])
    texts = _texts(dlg)

    assert "SUPPRIMER" in texts
    assert "Supprimer Partage ventes ?" in texts
    assert "Supprimer ce profil FTP ?" in texts


def test_dialog_with_usage_lists_pipeline_names(qapp):
    from ui.dialogs import ConnectionDeleteDialog

    dlg = ConnectionDeleteDialog(None, "SFTP", "SFTP Partenaire",
                                  ["Reporting ventes J-1", "Dépôt partenaire hebdo"])
    text = " ".join(_texts(dlg))

    assert "Reporting ventes J-1" in text
    assert "Dépôt partenaire hebdo" in text
    assert "2 pipelines" in text


def test_dialog_with_bastion_users_shows_direct_connection_note(qapp):
    from ui.dialogs import ConnectionDeleteDialog

    dlg = ConnectionDeleteDialog(None, "SSH", "Bastion DMZ", [], bastion_users=["Edge Hadoop"])
    text = " ".join(_texts(dlg))

    assert "Edge Hadoop" in text
    assert "connexion directe" in text


def test_dialog_delete_button_is_danger_styled_and_labeled(qapp):
    from ui.dialogs import ConnectionDeleteDialog

    dlg = ConnectionDeleteDialog(None, "FTP", "Partage ventes", [])

    assert dlg.btn_delete.objectName() == "danger"
    assert dlg.btn_delete.text() == "Supprimer quand même"


def test_confirm_delete_uses_the_new_dialog_not_a_message_box(qapp, test_db, monkeypatch):
    from PySide6.QtWidgets import QDialog
    from ui.dialogs import ConnectionDeleteDialog
    from ui.main_window.connections_view import ConnectionsView

    p = db.create_ftp_profile(name="FTP-confirm", host="h", port=21, username="u", password="pw")

    captured = {}
    def fake_exec(self):
        captured["ran"] = True
        return QDialog.Accepted
    monkeypatch.setattr(ConnectionDeleteDialog, "exec", fake_exec)

    view = ConnectionsView()
    view._on_delete_ftp(p.id)

    assert captured.get("ran")
    assert db.get_ftp_profile(p.id) is None   # accepté -> bien supprimé
