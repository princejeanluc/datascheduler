"""
DataScheduler — tests/test_condition_step.py
Évaluateur d'expression de ConditionStep (chantier 6a) : pas d'eval() — une grammaire minimale
"<champ> <opérateur> <valeur>" sur rows_count / artifact:<nom>.
"""

from core.steps import get_step
from core.steps.base import StepContext


def test_rows_count_comparison_true():
    ctx = StepContext()
    ctx.rows_count = 5
    result = get_step("CONDITION", {"expression": "rows_count > 0"}).run(ctx)
    assert result.success
    assert result.active_port == "true"


def test_rows_count_comparison_false():
    ctx = StepContext()
    ctx.rows_count = 0
    result = get_step("CONDITION", {"expression": "rows_count > 0"}).run(ctx)
    assert result.success
    assert result.active_port == "false"


def test_equality_and_inequality_operators():
    ctx = StepContext()
    ctx.rows_count = 10
    assert get_step("CONDITION", {"expression": "rows_count == 10"}).run(ctx).active_port == "true"
    assert get_step("CONDITION", {"expression": "rows_count != 10"}).run(ctx).active_port == "false"
    assert get_step("CONDITION", {"expression": "rows_count >= 10"}).run(ctx).active_port == "true"
    assert get_step("CONDITION", {"expression": "rows_count <= 9"}).run(ctx).active_port == "false"


def test_artifact_presence():
    ctx = StepContext()
    ctx.artifacts["result"] = "some/path.csv"
    result = get_step("CONDITION", {"expression": 'artifact:result != ""'}).run(ctx)
    assert result.success
    assert result.active_port == "true"


def test_artifact_missing_compares_as_none():
    ctx = StepContext()
    result = get_step("CONDITION", {"expression": 'artifact:missing != ""'}).run(ctx)
    # None != "" est vrai en Python — vérifie juste qu'aucune exception ne remonte.
    assert result.success


def test_empty_expression_is_rejected_without_raising():
    ctx = StepContext()
    result = get_step("CONDITION", {"expression": ""}).run(ctx)
    assert not result.success
    assert result.error


def test_unrecognized_expression_is_rejected_without_raising():
    ctx = StepContext()
    result = get_step("CONDITION", {"expression": "n'importe quoi !!!"}).run(ctx)
    assert not result.success
    assert "Expression invalide" in result.error


def test_no_eval_of_arbitrary_code():
    """Une expression tentant d'invoquer du code Python arbitraire doit être rejetée
    proprement, pas exécutée — confirme l'absence d'eval()."""
    ctx = StepContext()
    result = get_step("CONDITION", {"expression": "__import__('os').system('echo pwned')"}).run(ctx)
    assert not result.success
