"""
DataScheduler — tests/test_sql_query_dialog.py
SqlQueryDialog (modale rapide "+ Nouvelle requête SQL") — vérifie qu'elle utilise bien
SqlEditorWidget (chantier atelier SQL, partagé avec l'atelier), et son comportement de
sauvegarde/validation, inchangé depuis avant le refactor.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_uses_shared_sql_editor_widget(qapp, test_db):
    from ui.dialogs.sql_query_dialog import SqlQueryDialog
    from ui.sql_editor import SqlEditorWidget

    dlg = SqlQueryDialog()
    assert isinstance(dlg.editor, SqlEditorWidget)


def test_save_creates_a_new_query(qapp, test_db):
    from ui.dialogs.sql_query_dialog import SqlQueryDialog

    dlg = SqlQueryDialog()
    dlg.inp_name.setText("NOUVELLE_REQUETE")
    dlg.inp_desc.setText("desc")
    dlg.editor.set_text("SELECT 1 FROM dual")

    accepted = []
    dlg.accept = lambda: accepted.append(1)
    dlg._on_save()

    assert accepted == [1]
    queries = db.get_sql_queries()
    assert len(queries) == 1
    assert queries[0].name == "NOUVELLE_REQUETE"
    assert queries[0].sql_text == "SELECT 1 FROM dual"


def test_save_rejects_empty_name(qapp, test_db):
    from ui.dialogs.sql_query_dialog import SqlQueryDialog

    dlg = SqlQueryDialog()
    dlg.editor.set_text("SELECT 1")
    accepted = []
    dlg.accept = lambda: accepted.append(1)
    dlg._on_save()

    assert accepted == []
    assert db.get_sql_queries() == []


def test_save_rejects_empty_sql(qapp, test_db):
    from ui.dialogs.sql_query_dialog import SqlQueryDialog

    dlg = SqlQueryDialog()
    dlg.inp_name.setText("X")
    accepted = []
    dlg.accept = lambda: accepted.append(1)
    dlg._on_save()

    assert accepted == []
    assert db.get_sql_queries() == []


def test_editing_existing_query_prefills_and_updates(qapp, test_db):
    from ui.dialogs.sql_query_dialog import SqlQueryDialog

    q = db.create_sql_query(name="ORIGINAL", sql_text="SELECT 1", description="d")
    dlg = SqlQueryDialog(query=q)
    assert dlg.inp_name.text() == "ORIGINAL"
    assert dlg.editor.text() == "SELECT 1"

    dlg.inp_name.setText("RENOMMEE")
    dlg.editor.set_text("SELECT 2")
    accepted = []
    dlg.accept = lambda: accepted.append(1)
    dlg._on_save()

    assert accepted == [1]
    reloaded = db.get_sql_query(q.id)
    assert reloaded.name == "RENOMMEE"
    assert reloaded.sql_text == "SELECT 2"


def test_format_button_reformats_editor_content(qapp, test_db):
    from ui.dialogs.sql_query_dialog import SqlQueryDialog

    dlg = SqlQueryDialog()
    dlg.editor.set_text("select a from t")
    dlg.editor.format_sql()
    assert "SELECT" in dlg.editor.text()


def test_eyebrow_shown_only_when_step_label_and_pipeline_name_are_both_provided(qapp, test_db):
    """A10 (Requêtes SQL) : surtitre contextuel (« NOUVELLE REQUÊTE · POUR L'ÉTAPE « X » DE Y »)
    uniquement quand l'appelant fournit les deux paramètres facultatifs — signature actuelle
    (parent=None, query=None) conservée en tête pour les appelants qui ne les fournissent pas."""
    from PySide6.QtWidgets import QLabel
    from ui.dialogs.sql_query_dialog import SqlQueryDialog

    dlg_plain = SqlQueryDialog()
    assert not any("NOUVELLE REQUÊTE" in lbl.text() for lbl in dlg_plain.findChildren(QLabel))

    dlg_contextual = SqlQueryDialog(step_label="Extraire les retours",
                                     pipeline_name="Reporting ventes J-1")
    texts = [lbl.text() for lbl in dlg_contextual.findChildren(QLabel)]
    assert any("EXTRAIRE LES RETOURS" in t and "Reporting ventes J-1" in t for t in texts)
