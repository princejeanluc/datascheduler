"""
DataScheduler — tests/test_queries_view_workshop.py
QueriesView (chantier atelier SQL) : atelier maître-détail — remplace le tableau + dialogue modal
(voir tests/test_sql_query_dialog.py, supprimé : tests/test_queries_view_usage_column.py, écrit
contre l'ancien view.table qui n'existe plus).
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


def test_empty_state_shown_when_no_queries(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    view = QueriesView()
    assert not view._empty_label.isHidden()
    assert view.list_widget.isHidden()
    assert view._active_id is None


def test_loads_first_query_alphabetically_by_default(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    db.create_sql_query(name="ZEBRA", sql_text="SELECT 1")
    db.create_sql_query(name="ALPHA", sql_text="SELECT 2")
    view = QueriesView()
    assert view.inp_name.text() == "ALPHA"
    assert view.editor.text() == "SELECT 2"


def test_select_query_loads_it_into_the_workshop(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    q1 = db.create_sql_query(name="Q1", sql_text="SELECT 1", description="premiere")
    q2 = db.create_sql_query(name="Q2", sql_text="SELECT 2", description="seconde")
    view = QueriesView()
    view._select_query(q2.id)
    assert view.inp_name.text() == "Q2"
    assert view.inp_desc.text() == "seconde"
    assert view.editor.text() == "SELECT 2"
    view._select_query(q1.id)
    assert view.inp_name.text() == "Q1"


def test_search_matches_name_description_and_sql_body(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    db.create_sql_query(name="VENTES", sql_text="SELECT * FROM ventes", description="chiffre")
    db.create_sql_query(name="STOCK", sql_text="SELECT * FROM stock_telco", description="inventaire")
    view = QueriesView()

    def visible_names():
        names = []
        for i in range(view.list_widget.count()):
            item = view.list_widget.item(i)
            if not item.isHidden():
                names.append(view.list_widget.itemWidget(item).query_id)
        return names

    view.inp_search.setText("stock_telco")   # présent uniquement dans le corps SQL
    assert len(visible_names()) == 1

    view.inp_search.setText("chiffre")   # présent uniquement dans la description
    assert len(visible_names()) == 1

    view.inp_search.setText("")
    assert len(visible_names()) == 2


def test_usage_pill_reflects_pipelines_using_the_query(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    q = db.create_sql_query(name="Q", sql_text="SELECT 1")
    view = QueriesView()
    assert view.lbl_usage.text() == "Aucun pipeline"

    p = db.create_pipeline(name="p-using-q")
    db.save_steps(p.id, [{"step_type": "DB_EXTRACT", "config": {"sql_query_id": q.id}}])
    view.refresh()
    assert view.lbl_usage.text() == "1 pipeline(s)"


def test_new_query_creates_a_row_and_selects_it(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    view = QueriesView()
    view._on_new_query()
    assert view.list_widget.count() == 1
    assert view._active_id is not None
    assert view.inp_name.text().startswith("NOUVELLE_REQUETE")


def test_new_query_disambiguates_name_on_repeated_creation(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    view = QueriesView()
    view._on_new_query()
    view._on_new_query()
    names = {q.name for q in db.get_sql_queries()}
    assert "NOUVELLE_REQUETE" in names
    assert "NOUVELLE_REQUETE_2" in names


def test_duplicate_creates_a_second_query_and_selects_it(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    q = db.create_sql_query(name="ORIGINAL", sql_text="SELECT 1")
    view = QueriesView()
    view._select_query(q.id)
    view._on_duplicate_query()
    assert view.list_widget.count() == 2
    assert view.inp_name.text() == "ORIGINAL (copie)"
    assert view._active_id != q.id


def test_delete_without_usage_prompts_and_removes(qapp, test_db, monkeypatch):
    from ui.main_window.queries_view import QueriesView
    from PySide6.QtWidgets import QMessageBox

    q = db.create_sql_query(name="Q", sql_text="SELECT 1")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.Yes)
    view = QueriesView()
    view._on_delete_query(q.id)
    assert db.get_sql_queries() == []
    assert view.list_widget.count() == 0
    assert not view._empty_label.isHidden()


def test_delete_declined_keeps_the_query(qapp, test_db, monkeypatch):
    from ui.main_window.queries_view import QueriesView
    from PySide6.QtWidgets import QMessageBox

    q = db.create_sql_query(name="Q", sql_text="SELECT 1")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.No)
    view = QueriesView()
    view._on_delete_query(q.id)
    assert len(db.get_sql_queries()) == 1


def test_delete_warns_when_used_by_pipelines(qapp, test_db, monkeypatch):
    from ui.main_window.queries_view import QueriesView
    from PySide6.QtWidgets import QMessageBox

    q = db.create_sql_query(name="Q", sql_text="SELECT 1")
    p = db.create_pipeline(name="p-using-q")
    db.save_steps(p.id, [{"step_type": "DB_EXTRACT", "config": {"sql_query_id": q.id}}])

    captured = {}
    def fake_question(_self, _title, msg, *_a, **_kw):
        captured["msg"] = msg
        return QMessageBox.Yes
    monkeypatch.setattr(QMessageBox, "question", fake_question)

    view = QueriesView()
    view._on_delete_query(q.id)
    assert "p-using-q" in captured["msg"]
    assert db.get_sql_queries() == []


def test_save_persists_name_description_sql_and_profile(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    profile = db.create_oracle_profile(name="ORA1", host="h", port=1521, username="u",
                                       password="p", service_name="S")
    q = db.create_sql_query(name="Q", sql_text="SELECT 1")
    view = QueriesView()
    view._select_query(q.id)
    view.inp_name.setText("RENOMMEE")
    view.inp_desc.setText("nouvelle description")
    view.editor.set_text("SELECT 2 FROM dual")
    idx = view.cb_oracle.findData(profile.id)
    view.cb_oracle.setCurrentIndex(idx)
    view._on_save_query()

    reloaded = db.get_sql_query(q.id)
    assert reloaded.name == "RENOMMEE"
    assert reloaded.description == "nouvelle description"
    assert reloaded.sql_text == "SELECT 2 FROM dual"
    assert reloaded.oracle_profile_id == profile.id


def test_save_rejects_empty_name(qapp, test_db, monkeypatch):
    from ui.main_window.queries_view import QueriesView
    from PySide6.QtWidgets import QMessageBox

    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: warnings.append(a) or None)

    q = db.create_sql_query(name="Q", sql_text="SELECT 1")
    view = QueriesView()
    view._select_query(q.id)
    view.inp_name.setText("")
    view._on_save_query()

    assert warnings
    assert db.get_sql_query(q.id).name == "Q"


def test_save_rejects_empty_sql(qapp, test_db, monkeypatch):
    from ui.main_window.queries_view import QueriesView
    from PySide6.QtWidgets import QMessageBox

    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: warnings.append(a) or None)

    q = db.create_sql_query(name="Q", sql_text="SELECT 1")
    view = QueriesView()
    view._select_query(q.id)
    view.editor.set_text("")
    view._on_save_query()

    assert warnings
    assert db.get_sql_query(q.id).sql_text == "SELECT 1"


def test_format_button_reformats_editor_content(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    q = db.create_sql_query(name="Q", sql_text="select a from t")
    view = QueriesView()
    view._select_query(q.id)
    view.btn_format.click()
    assert "SELECT" in view.editor.text()


def test_import_sql_loads_file_content_into_editor(qapp, test_db, monkeypatch, tmp_path):
    from ui.main_window.queries_view import QueriesView
    from PySide6.QtWidgets import QFileDialog

    sql_file = tmp_path / "imported.sql"
    sql_file.write_text("SELECT imported_column FROM imported_table", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **kw: (str(sql_file), ""))

    q = db.create_sql_query(name="Q", sql_text="SELECT 1")
    view = QueriesView()
    view._select_query(q.id)
    view._on_import_sql()
    assert view.editor.text() == "SELECT imported_column FROM imported_table"


def test_export_sql_writes_editor_content_to_file(qapp, test_db, monkeypatch, tmp_path):
    from ui.main_window.queries_view import QueriesView
    from PySide6.QtWidgets import QFileDialog

    dest = tmp_path / "exported.sql"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **kw: (str(dest), ""))

    q = db.create_sql_query(name="Q", sql_text="SELECT exported_column FROM t")
    view = QueriesView()
    view._select_query(q.id)
    view._on_export_sql()
    assert dest.read_text(encoding="utf-8") == "SELECT exported_column FROM t"


def test_workshop_disabled_when_no_query_selected(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    view = QueriesView()
    assert not view._workshop.isEnabled()
