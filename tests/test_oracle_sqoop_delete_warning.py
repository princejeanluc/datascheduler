"""
DataScheduler — tests/test_oracle_sqoop_delete_warning.py
Correctif K1 (docs/refonte/LOTS.md) : supprimer un profil Oracle utilisé uniquement par une
étape Sqoop (clé "oracle_profile_id", sans "db_type") doit avertir l'utilisateur, exactement
comme pour un usage par une étape DB_EXTRACT/DB_EXECUTE/DB_LOAD (clé "profile_id" + "db_type").
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_delete_oracle_profile_warns_about_sqoop_export_usage(qapp, test_db, monkeypatch):
    from ui.main_window.connections_view import ConnectionsView

    profile = db.create_oracle_profile(name="ORA1", host="h", port=1521, username="u", password="p")
    pipeline = db.create_pipeline(name="pipeline-sqoop")
    db.save_steps(pipeline.id, [
        {"step_type": "SQOOP_EXPORT", "config": {"oracle_profile_id": profile.id}},
    ])

    captured = {}
    def fake_question(_self, _title, msg, *_a, **_kw):
        captured["msg"] = msg
        return QMessageBox.No   # décliner : ne pas réellement supprimer
    monkeypatch.setattr(QMessageBox, "question", fake_question)

    view = ConnectionsView()
    view._on_delete_database(profile.id, "ORACLE")

    assert "pipeline-sqoop" in captured["msg"]
    assert db.get_oracle_profiles() != []   # décliné : le profil existe toujours


def test_delete_oracle_profile_warns_about_sqoop_import_usage(qapp, test_db, monkeypatch):
    from ui.main_window.connections_view import ConnectionsView

    profile = db.create_oracle_profile(name="ORA2", host="h", port=1521, username="u", password="p")
    pipeline = db.create_pipeline(name="pipeline-sqoop-import")
    db.save_steps(pipeline.id, [
        {"step_type": "SQOOP_IMPORT", "config": {"oracle_profile_id": profile.id}},
    ])

    captured = {}
    def fake_question(_self, _title, msg, *_a, **_kw):
        captured["msg"] = msg
        return QMessageBox.No
    monkeypatch.setattr(QMessageBox, "question", fake_question)

    view = ConnectionsView()
    view._on_delete_database(profile.id, "ORACLE")

    assert "pipeline-sqoop-import" in captured["msg"]


def test_delete_oracle_profile_without_usage_does_not_warn(qapp, test_db, monkeypatch):
    """Non-régression : un profil non utilisé reste supprimable sans avertissement d'usage."""
    from ui.main_window.connections_view import ConnectionsView

    profile = db.create_oracle_profile(name="ORA3", host="h", port=1521, username="u", password="p")

    captured = {}
    def fake_question(_self, _title, msg, *_a, **_kw):
        captured["msg"] = msg
        return QMessageBox.Yes
    monkeypatch.setattr(QMessageBox, "question", fake_question)

    view = ConnectionsView()
    view._on_delete_database(profile.id, "ORACLE")

    assert "utilisé par" not in captured["msg"]
    assert db.get_oracle_profiles() == []   # confirmé : bien supprimé
