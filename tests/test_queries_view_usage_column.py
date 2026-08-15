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
from PySide6.QtWidgets import QApplication, QHeaderView

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
    """Aperçu SQL coloré (chantier identité, vague 2, idée 12) — l'infobulle contient désormais du
    HTML (mots-clés colorés), donc le texte brut apparaît DANS le rendu plutôt qu'en égalité
    stricte avec le contenu de la cellule."""
    from ui.main_window.queries_view import QueriesView

    db.create_sql_query(name="preview-query", sql_text="SELECT * FROM my_table WHERE x = 1")
    view = QueriesView()
    tooltip = view.table.item(0, 0).toolTip()
    assert "SELECT" in tooltip and "my_table" in tooltip and "WHERE" in tooltip
    assert "<span" in tooltip


def test_highlight_sql_html_wraps_keywords_and_escapes_html():
    from ui.main_window.queries_view import _highlight_sql_html
    from ui.styles import COLORS

    result = _highlight_sql_html("SELECT * FROM t WHERE x < 1")
    assert f'color:{COLORS["accent"]}' in result
    assert "<span" in result
    # "<" dans le SQL doit être échappé, jamais interprété comme une balise HTML.
    assert "&lt;" in result


def test_actions_column_width_is_fixed_not_auto_shrunk(qapp, test_db):
    """Même correctif que PipelinesView (voir test_pipelines_view_action_menu.py) : la colonne
    Actions doit rester en mode Fixed, pas ResizeToContents, pour ne pas se faire recalculer
    trop étroite pour ses 2 boutons par Qt."""
    from ui.main_window.queries_view import QueriesView

    db.create_sql_query(name="fixed-width-test", sql_text="SELECT 1")
    view = QueriesView()
    mode = view.table.horizontalHeader().sectionResizeMode(3)
    assert mode == QHeaderView.Fixed
    assert view.table.columnWidth(3) >= 80
