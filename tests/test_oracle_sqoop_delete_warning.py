"""
DataScheduler — tests/test_oracle_sqoop_delete_warning.py
Correctif K1 (docs/refonte/LOTS.md) : supprimer un profil Oracle utilisé uniquement par une
étape Sqoop (clé "oracle_profile_id", sans "db_type") doit avertir l'utilisateur, exactement
comme pour un usage par une étape DB_EXTRACT/DB_EXECUTE/DB_LOAD (clé "profile_id" + "db_type").

Depuis le lot A-Connexions (A11), l'avertissement est un `ConnectionDeleteDialog` (pas un
`QMessageBox.question`) — les tests patchent `ConnectionDeleteDialog.exec` et lisent son contenu
via ses `QLabel`, pas le texte d'un message box.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _texts(widget) -> list:
    return [lbl.text() for lbl in widget.findChildren(QLabel) if lbl.text()]


def test_delete_oracle_profile_warns_about_sqoop_export_usage(qapp, test_db, monkeypatch):
    from ui.dialogs import ConnectionDeleteDialog
    from ui.main_window.connections_view import ConnectionsView

    profile = db.create_oracle_profile(name="ORA1", host="h", port=1521, username="u", password="p")
    pipeline = db.create_pipeline(name="pipeline-sqoop")
    db.save_steps(pipeline.id, [
        {"step_type": "SQOOP_EXPORT", "config": {"oracle_profile_id": profile.id}},
    ])

    captured = {}
    def fake_exec(self):
        captured["texts"] = _texts(self)
        return QDialog.Rejected   # décliner : ne pas réellement supprimer
    monkeypatch.setattr(ConnectionDeleteDialog, "exec", fake_exec)

    view = ConnectionsView()
    view._on_delete_database(profile.id, "ORACLE")

    assert "pipeline-sqoop" in " ".join(captured["texts"])
    assert db.get_oracle_profiles() != []   # décliné : le profil existe toujours


def test_delete_oracle_profile_warns_about_sqoop_import_usage(qapp, test_db, monkeypatch):
    from ui.dialogs import ConnectionDeleteDialog
    from ui.main_window.connections_view import ConnectionsView

    profile = db.create_oracle_profile(name="ORA2", host="h", port=1521, username="u", password="p")
    pipeline = db.create_pipeline(name="pipeline-sqoop-import")
    db.save_steps(pipeline.id, [
        {"step_type": "SQOOP_IMPORT", "config": {"oracle_profile_id": profile.id}},
    ])

    captured = {}
    def fake_exec(self):
        captured["texts"] = _texts(self)
        return QDialog.Rejected
    monkeypatch.setattr(ConnectionDeleteDialog, "exec", fake_exec)

    view = ConnectionsView()
    view._on_delete_database(profile.id, "ORACLE")

    assert "pipeline-sqoop-import" in " ".join(captured["texts"])


def test_database_table_usage_column_counts_sqoop_steps_too(qapp, test_db):
    """A6 (refonte, lot A-Connexions) : la colonne « Utilisée par » du tableau principal doit
    rester cohérente avec l'avertissement de suppression ci-dessus — un profil Oracle utilisé
    uniquement par une étape Sqoop ne doit pas afficher « aucun pipeline »."""
    from PySide6.QtWidgets import QLabel

    from ui.main_window.connections_view import ConnectionsView

    profile = db.create_oracle_profile(name="ORA-SQOOP", host="h", port=1521, username="u", password="p")
    pipeline = db.create_pipeline(name="pipeline-sqoop-usage")
    db.save_steps(pipeline.id, [
        {"step_type": "SQOOP_EXPORT", "config": {"oracle_profile_id": profile.id}},
    ])

    view = ConnectionsView()
    usage_widget = view.database_table.cellWidget(0, 4)
    assert isinstance(usage_widget, QLabel)
    assert usage_widget.text() == "1 pipeline"


def test_delete_oracle_profile_without_usage_does_not_warn(qapp, test_db, monkeypatch):
    """Non-régression : un profil non utilisé reste supprimable sans avertissement d'usage."""
    from ui.dialogs import ConnectionDeleteDialog
    from ui.main_window.connections_view import ConnectionsView

    profile = db.create_oracle_profile(name="ORA3", host="h", port=1521, username="u", password="p")

    captured = {}
    def fake_exec(self):
        captured["texts"] = _texts(self)
        return QDialog.Accepted
    monkeypatch.setattr(ConnectionDeleteDialog, "exec", fake_exec)

    view = ConnectionsView()
    view._on_delete_database(profile.id, "ORACLE")

    assert "Supprimer ce profil Oracle ?" in captured["texts"]
    assert db.get_oracle_profiles() == []   # confirmé : bien supprimé
