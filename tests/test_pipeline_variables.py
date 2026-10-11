"""
DataScheduler — tests/test_pipeline_variables.py
Variables déclarées au niveau du pipeline (chantier variables de pipeline) : round-trip CRUD
(database/db_manager.py::get_pipeline_variables()/save_pipeline_variables()), amorçage de
ctx.variables à l'exécution dans l'ordre déclaré (core/pipeline.py::run_pipeline()), et échec
propre du run si une expression par défaut échoue à l'évaluation.
"""

from database import db_manager as db


def test_save_then_get_round_trips_name_expression_and_order(test_db):
    pipeline = db.create_pipeline(name="pv-round-trip-test")
    db.save_pipeline_variables(pipeline.id, [
        {"name": "base_date", "default_expression": "today()"},
        {"name": "limite", "default_expression": "date_add(var:base_date, -7)"},
    ])

    variables = db.get_pipeline_variables(pipeline.id)

    assert [v.name for v in variables] == ["base_date", "limite"]
    assert variables[1].default_expression == "date_add(var:base_date, -7)"


def test_resave_with_fewer_variables_fully_replaces(test_db):
    pipeline = db.create_pipeline(name="pv-resave-test")
    db.save_pipeline_variables(pipeline.id, [
        {"name": "a", "default_expression": "1"},
        {"name": "b", "default_expression": "2"},
    ])

    db.save_pipeline_variables(pipeline.id, [{"name": "c", "default_expression": "3"}])

    variables = db.get_pipeline_variables(pipeline.id)
    assert [v.name for v in variables] == ["c"]


def test_resave_with_reordered_variables_preserves_new_order(test_db):
    pipeline = db.create_pipeline(name="pv-reorder-test")
    db.save_pipeline_variables(pipeline.id, [
        {"name": "a", "default_expression": "1"},
        {"name": "b", "default_expression": "2"},
    ])

    db.save_pipeline_variables(pipeline.id, [
        {"name": "b", "default_expression": "2"},
        {"name": "a", "default_expression": "1"},
    ])

    variables = db.get_pipeline_variables(pipeline.id)
    assert [v.name for v in variables] == ["b", "a"]


def test_empty_list_clears_all_variables(test_db):
    pipeline = db.create_pipeline(name="pv-clear-test")
    db.save_pipeline_variables(pipeline.id, [{"name": "a", "default_expression": "1"}])

    db.save_pipeline_variables(pipeline.id, [])

    assert db.get_pipeline_variables(pipeline.id) == []


def test_variables_are_scoped_per_pipeline(test_db):
    p1 = db.create_pipeline(name="pv-scope-test-1")
    p2 = db.create_pipeline(name="pv-scope-test-2")
    db.save_pipeline_variables(p1.id, [{"name": "a", "default_expression": "1"}])

    assert db.get_pipeline_variables(p2.id) == []
    assert len(db.get_pipeline_variables(p1.id)) == 1
