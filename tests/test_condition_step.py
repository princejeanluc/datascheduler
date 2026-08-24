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


# ──────────────────────────────────────────────
#  Composition booléenne (chantier vocabulaire des conditions) — and/or/not/parenthèses
# ──────────────────────────────────────────────

def test_and_composition():
    ctx = StepContext()
    ctx.rows_count = 5
    ctx.artifacts["r"] = "some/path.csv"
    true_expr = 'rows_count > 0 and artifact:r != ""'
    # artifact:missing != "" évalue à True (None != "" est vrai en Python — voir
    # test_artifact_missing_compares_as_none), donc rows_count < 0 sert de membre réellement faux.
    false_expr = "rows_count > 0 and rows_count < 0"
    assert get_step("CONDITION", {"expression": true_expr}).run(ctx).active_port == "true"
    assert get_step("CONDITION", {"expression": false_expr}).run(ctx).active_port == "false"


def test_or_composition():
    ctx = StepContext()
    ctx.rows_count = 0
    true_expr = "rows_count > 0 or rows_count == 0"
    false_expr = "rows_count > 0 or rows_count < 0"
    assert get_step("CONDITION", {"expression": true_expr}).run(ctx).active_port == "true"
    assert get_step("CONDITION", {"expression": false_expr}).run(ctx).active_port == "false"


def test_not_negates_a_comparison():
    ctx = StepContext()
    ctx.rows_count = 0
    result = get_step("CONDITION", {"expression": "not rows_count > 0"}).run(ctx)
    assert result.success
    assert result.active_port == "true"


def test_and_binds_tighter_than_or_by_default():
    """rows_count == 1 or rows_count == 2 and rows_count == 3, avec rows_count=1 : si `and` est
    bien prioritaire, ça donne `1==1 or (2==3 and False)` = True or False = True. Si l'ordre était
    inversé (or d'abord), ça donnerait `(1==1 or 1==2) and 1==3` = True and False = False — les
    deux lectures donnent un résultat DIFFÉRENT, donc ce test discrimine vraiment la précédence."""
    ctx = StepContext()
    ctx.rows_count = 1
    expr = "rows_count == 1 or rows_count == 2 and rows_count == 3"
    result = get_step("CONDITION", {"expression": expr}).run(ctx)
    assert result.success
    assert result.active_port == "true"


def test_parentheses_override_default_precedence():
    """Même expression que ci-dessus, mais parenthésée pour forcer le `or` en premier :
    (rows_count == 1 or rows_count == 2) and rows_count == 3, avec rows_count=1, donne
    True and False = False — l'inverse du résultat sans parenthèses."""
    ctx = StepContext()
    ctx.rows_count = 1
    expr = "(rows_count == 1 or rows_count == 2) and rows_count == 3"
    result = get_step("CONDITION", {"expression": expr}).run(ctx)
    assert result.success
    assert result.active_port == "false"


def test_nested_parentheses():
    ctx = StepContext()
    ctx.rows_count = 5
    expr = "((rows_count > 0 and rows_count < 10) or rows_count == 99) and not rows_count == 0"
    result = get_step("CONDITION", {"expression": expr}).run(ctx)
    assert result.success
    assert result.active_port == "true"


def test_quoted_string_containing_keyword_words_is_never_mistaken_for_an_operator():
    """Régression ciblée : 'and' à l'intérieur d'une chaîne citée ne doit jamais être traité
    comme le mot-clé booléen — c'est exactement le trou de l'ancien découpage par sous-chaîne
    que le nouveau tokenizer doit fermer."""
    ctx = StepContext()
    ctx.artifacts["label"] = "sales and marketing"
    result = get_step("CONDITION", {"expression": 'artifact:label == "sales and marketing"'}).run(ctx)
    assert result.success
    assert result.active_port == "true"


def test_artifact_name_with_uuid_style_hyphens_unquoted():
    """ctx.artifacts est le plus souvent peuplé par _step_key, un UUID — donc avec des tirets.
    Doit continuer à fonctionner sans avoir à citer le nom."""
    ctx = StepContext()
    ctx.artifacts["a1b2-c3d4-e5f6"] = "some/path.csv"
    result = get_step("CONDITION", {"expression": 'artifact:a1b2-c3d4-e5f6 != ""'}).run(ctx)
    assert result.success
    assert result.active_port == "true"


def test_artifact_name_with_space_requires_quoting():
    """output_name est un champ texte libre côté UI, sans restriction — un nom avec espace doit
    être cité pour rester un seul opérande."""
    ctx = StepContext()
    ctx.artifacts["rapport final"] = "some/path.csv"
    result = get_step("CONDITION", {"expression": 'artifact:"rapport final" != ""'}).run(ctx)
    assert result.success
    assert result.active_port == "true"


def test_deeply_nested_parentheses_raise_cleanly_instead_of_recursion_error():
    ctx = StepContext()
    expr = "(" * 100 + "rows_count > 0" + ")" * 100
    result = get_step("CONDITION", {"expression": expr}).run(ctx)
    assert not result.success
    assert "Expression invalide" in result.error


def test_empty_parentheses_are_rejected_cleanly():
    ctx = StepContext()
    result = get_step("CONDITION", {"expression": "()"}).run(ctx)
    assert not result.success
    assert "Expression invalide" in result.error


def test_dangling_comparison_operator_is_rejected_cleanly():
    ctx = StepContext()
    result = get_step("CONDITION", {"expression": "rows_count >"}).run(ctx)
    assert not result.success
    assert "Expression invalide" in result.error


def test_trailing_boolean_keyword_is_rejected_cleanly():
    ctx = StepContext()
    result = get_step("CONDITION", {"expression": "rows_count > 0 and"}).run(ctx)
    assert not result.success
    assert "Expression invalide" in result.error


def test_unmatched_opening_parenthesis_is_rejected_cleanly():
    ctx = StepContext()
    result = get_step("CONDITION", {"expression": "(rows_count > 0"}).run(ctx)
    assert not result.success
    assert "Expression invalide" in result.error
