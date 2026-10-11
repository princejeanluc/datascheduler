"""
DataScheduler — tests/test_pipeline_variables.py
Variables déclarées au niveau du pipeline (chantier variables de pipeline) : round-trip CRUD
(database/db_manager.py::get_pipeline_variables()/save_pipeline_variables()), amorçage de
ctx.variables à l'exécution dans l'ordre déclaré (core/pipeline.py::run_pipeline()), et échec
propre du run si une expression par défaut échoue à l'évaluation.
"""

from pathlib import Path

from database import db_manager as db
import core.steps as steps_module
from core.steps.base import BaseStep, StepResult
from core.pipeline import run_pipeline


class _FakeMarkerStep(BaseStep):
    """Écrit la valeur d'une variable de ctx (ou un marqueur fixe) dans un fichier — sert à
    prouver, sans dépendre d'un vrai type d'étape, qu'une variable de pipeline amorcée est bien
    visible dans ctx.variables au moment où la première étape s'exécute (ou, à l'inverse, qu'une
    étape n'a jamais tourné si l'amorçage a échoué avant)."""

    def run(self, ctx, cancel_event=None, on_progress=None) -> StepResult:
        path = Path(self.config["path"])
        value = ctx.variables.get(self.config["var_name"]) if self.config.get("var_name") else "ran"
        path.write_text(str(value))
        return StepResult(success=True)


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


# ──────────────────────────────────────────────
#  Amorçage à l'exécution (core/pipeline.py::run_pipeline())
# ──────────────────────────────────────────────

def test_seeding_populates_ctx_variables_before_the_first_step(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeMarkerStep)
    pipeline = db.create_pipeline(name="pv-seed-visible-test")
    db.save_pipeline_variables(pipeline.id, [{"name": "env", "default_expression": '"PROD"'}])
    out = tmp_path / "out.txt"
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(out), "var_name": "env"}},
    ])

    result = run_pipeline(pipeline.id)

    assert result.success, result.error
    assert out.read_text() == "PROD"


def test_seeding_evaluates_in_declared_order_so_a_later_variable_can_reference_an_earlier_one(
    test_db, monkeypatch, tmp_path,
):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeMarkerStep)
    pipeline = db.create_pipeline(name="pv-seed-order-test")
    db.save_pipeline_variables(pipeline.id, [
        {"name": "base", "default_expression": "10"},
        {"name": "derived", "default_expression": "var:base + 5"},
    ])
    out = tmp_path / "out.txt"
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(out), "var_name": "derived"}},
    ])

    result = run_pipeline(pipeline.id)

    assert result.success, result.error
    assert out.read_text() == "15"


def test_seeding_failure_aborts_the_run_before_any_step_and_before_create_run(
    test_db, monkeypatch, tmp_path,
):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeMarkerStep)
    pipeline = db.create_pipeline(name="pv-seed-failure-test")
    db.save_pipeline_variables(pipeline.id, [{"name": "x", "default_expression": "1 / 0"}])
    marker = tmp_path / "ran.txt"
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(marker)}},
    ])

    result = run_pipeline(pipeline.id)

    assert not result.success
    assert "x" in result.error
    assert result.run_id is None       # aucune ligne PipelineRun créée
    assert not marker.exists()         # l'étape n'a jamais tourné
