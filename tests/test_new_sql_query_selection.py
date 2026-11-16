"""
DataScheduler — tests/test_new_sql_query_selection.py
Correctif K2 (docs/refonte/LOTS.md) : après "+ Nouvelle requête SQL" depuis un dialogue d'étape,
la requête sélectionnée doit être celle qui vient d'être créée — jamais `_sql_queries[-1]`
(dernière par ordre alphabétique, db.get_sql_queries() étant trié par nom).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

import ui.dialogs as dialogs_module
from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeSqlQueryDialog:
    """Simule SqlQueryDialog : la requête a déjà été créée (par le test, avant l'appel), le
    faux dialogue se contente d'exposer son id via result_query_id, comme le ferait le vrai
    dialogue après _on_save()."""
    def __init__(self, new_query_id):
        self._new_query_id = new_query_id
        self.result_query_id = None

    def __call__(self, parent=None, step_label=None, pipeline_name=None):
        self.result_query_id = self._new_query_id
        self.received_step_label = step_label
        self.received_pipeline_name = pipeline_name
        return self

    def exec(self):
        return True


def _install_fake_dialog(monkeypatch, new_query_id):
    monkeypatch.setattr(dialogs_module, "SqlQueryDialog", _FakeSqlQueryDialog(new_query_id))


def test_db_extract_selects_the_newly_created_query(qapp, test_db, monkeypatch):
    from ui.step_editor.db_extract_config_dialog import _DbExtractConfigDialog

    db.create_sql_query(name="Zzz_ancienne", sql_text="SELECT 1")
    new_query = db.create_sql_query(name="Aaa_nouvelle", sql_text="SELECT 2")
    _install_fake_dialog(monkeypatch, new_query.id)

    dlg = _DbExtractConfigDialog({}, None, "test-label")
    dlg._new_sql_query(dlg.cb_query)
    assert dlg.cb_query.currentData() == new_query.id


def test_db_extract_passes_step_label_and_pipeline_name_to_modal(qapp, test_db, monkeypatch):
    """A10 (Requêtes SQL) : la modale rapide reçoit le libellé de l'étape et le nom du pipeline
    en cours d'édition, pour son surtitre contextuel (paramètres facultatifs)."""
    from ui.step_editor.db_extract_config_dialog import _DbExtractConfigDialog

    new_query = db.create_sql_query(name="Q", sql_text="SELECT 1")
    fake = _FakeSqlQueryDialog(new_query.id)
    monkeypatch.setattr(dialogs_module, "SqlQueryDialog", fake)

    dlg = _DbExtractConfigDialog({}, None, "Extraire ventes J-1", pipeline_name="Reporting ventes J-1")
    dlg._new_sql_query(dlg.cb_query)
    assert fake.received_step_label == "Extraire ventes J-1"
    assert fake.received_pipeline_name == "Reporting ventes J-1"


def test_db_execute_selects_the_newly_created_query(qapp, test_db, monkeypatch):
    from ui.step_editor.db_execute_config_dialog import _DbExecuteConfigDialog

    db.create_sql_query(name="Zzz_ancienne", sql_text="SELECT 1")
    new_query = db.create_sql_query(name="Aaa_nouvelle", sql_text="SELECT 2")
    _install_fake_dialog(monkeypatch, new_query.id)

    dlg = _DbExecuteConfigDialog({}, None, "test-label")
    dlg._new_sql_query(dlg.cb_query)
    assert dlg.cb_query.currentData() == new_query.id


def test_spark_sql_selects_the_newly_created_query(qapp, test_db, monkeypatch):
    from ui.step_editor.spark_sql_config_dialog import _SparkSqlConfigDialog

    db.create_sql_query(name="Zzz_ancienne", sql_text="SELECT 1")
    new_query = db.create_sql_query(name="Aaa_nouvelle", sql_text="SELECT 2")
    _install_fake_dialog(monkeypatch, new_query.id)

    dlg = _SparkSqlConfigDialog({}, None, "test-label")
    dlg._new_sql_query(dlg.cb_query)
    assert dlg.cb_query.currentData() == new_query.id
