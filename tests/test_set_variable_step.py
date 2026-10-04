"""
DataScheduler — tests/test_set_variable_step.py
SetVariableStep (chantier SET_VARIABLE) : calcule une ou plusieurs variables via
core/expr_lang.py::evaluate(), sans dépendre d'un fichier amont. Mise à jour atomique de
ctx.variables — aucune écriture partielle si une assignation échoue en cours de route.
"""

from core.steps import get_step
from core.steps.base import StepContext


def test_single_literal_assignment():
    ctx = StepContext()
    result = get_step("SET_VARIABLE", {"assignments": [{"target": "x", "expression": "42"}]}).run(ctx)
    assert result.success
    assert ctx.variables == {"x": 42}


def test_multiple_assignments_in_one_step():
    ctx = StepContext()
    result = get_step("SET_VARIABLE", {"assignments": [
        {"target": "a", "expression": "1 + 1"},
        {"target": "b", "expression": '"text"'},
    ]}).run(ctx)
    assert result.success
    assert ctx.variables == {"a": 2, "b": "text"}


def test_expression_referencing_rows_count_and_existing_variable():
    ctx = StepContext()
    ctx.rows_count = 10
    ctx.variables["base"] = 5
    result = get_step("SET_VARIABLE", {"assignments": [
        {"target": "total", "expression": "rows_count + var:base"},
    ]}).run(ctx)
    assert result.success
    assert ctx.variables["total"] == 15


def test_expression_referencing_artifact():
    ctx = StepContext()
    ctx.artifacts["report"] = "some/path.csv"
    result = get_step("SET_VARIABLE", {"assignments": [
        {"target": "label", "expression": 'upper(artifact:report)'},
    ]}).run(ctx)
    assert result.success
    assert ctx.variables["label"] == "SOME/PATH.CSV"


def test_does_not_touch_ctx_output_file():
    ctx = StepContext()
    ctx.artifacts["output_file"] = "keep/me.csv"
    result = get_step("SET_VARIABLE", {"assignments": [{"target": "x", "expression": "1"}]}).run(ctx)
    assert result.success
    assert str(ctx.output_file) == "keep/me.csv"


def test_no_assignments_configured_is_rejected():
    ctx = StepContext()
    result = get_step("SET_VARIABLE", {"assignments": []}).run(ctx)
    assert not result.success
    assert "Aucune assignation" in result.error


def test_missing_target_is_rejected():
    ctx = StepContext()
    result = get_step("SET_VARIABLE", {"assignments": [{"target": "", "expression": "1"}]}).run(ctx)
    assert not result.success
    assert result.error


def test_invalid_expression_is_rejected_cleanly_naming_the_target():
    ctx = StepContext()
    result = get_step("SET_VARIABLE", {"assignments": [{"target": "x", "expression": "1 +"}]}).run(ctx)
    assert not result.success
    assert "x" in result.error


def test_atomic_update_aborts_all_assignments_if_one_fails():
    ctx = StepContext()
    result = get_step("SET_VARIABLE", {"assignments": [
        {"target": "a", "expression": "1"},
        {"target": "b", "expression": "1 / 0"},
    ]}).run(ctx)
    assert not result.success
    assert ctx.variables == {}   # "a" n'a jamais été écrit malgré son succès individuel


def test_no_eval_of_arbitrary_code():
    ctx = StepContext()
    result = get_step("SET_VARIABLE", {"assignments": [
        {"target": "x", "expression": "__import__('os').system('echo pwned')"},
    ]}).run(ctx)
    assert not result.success
