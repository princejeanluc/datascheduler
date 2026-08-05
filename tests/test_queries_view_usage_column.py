"""
DataScheduler — tests/test_queries_view_usage_column.py
Fumée (offscreen Qt) : la colonne "Profil Oracle associé" de QueriesView (chantier UX ergonomie,
E.5) était trompeuse depuis que SqlQuery est partagée par DB_EXTRACT/DB_EXECUTE (tout moteur) et
SPARK_SQL (aucun moteur) — remplacée par "Utilisée par N pipeline(s)", et un aperçu de la requête
en tooltip sur la cellule "Nom".
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


def test_usage_column_shows_aucun_when_unused(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    db.create_sql_query(name="unused-query", sql_text="SELECT 1")
    view = QueriesView()
    assert view.table.item(0, 2).text() == "Aucun"


def test_usage_column_counts_pipelines(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    q = db.create_sql_query(name="used-query", sql_text="SELECT 1")
    p1 = db.create_pipeline(name="pipeline-using-query-1")
    db.save_steps(p1.id, [{"step_type": "DB_EXTRACT", "config": {"sql_query_id": q.id}}])
    p2 = db.create_pipeline(name="pipeline-using-query-2")
    db.save_steps(p2.id, [{"step_type": "DB_EXECUTE", "config": {"sql_query_id": q.id}}])

    view = QueriesView()
    assert view.table.item(0, 2).text() == "2 pipeline(s)"
    assert "pipeline-using-query-1" in view.table.item(0, 2).toolTip()


def test_name_cell_tooltip_shows_sql_text(qapp, test_db):
    from ui.main_window.queries_view import QueriesView

    db.create_sql_query(name="preview-query", sql_text="SELECT * FROM my_table WHERE x = 1")
    view = QueriesView()
    assert view.table.item(0, 0).toolTip() == "SELECT * FROM my_table WHERE x = 1"
