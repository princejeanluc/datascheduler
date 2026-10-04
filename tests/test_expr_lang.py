"""
DataScheduler — tests/test_expr_lang.py
Évaluateur d'expressions partagé (core/expr_lang.py) : arithmétique, bibliothèque de fonctions,
désambiguïsation moins unaire/binaire, garde de récursion, découplage compile_expression()/
evaluate() (le premier ne doit jamais avoir besoin d'un ctx réel — c'est la propriété exploitée
par dry_run_pipeline()).
"""

from types import SimpleNamespace

import pytest

from core.expr_lang import compile_expression, evaluate


def _ctx(rows_count=0, artifacts=None, variables=None):
    return SimpleNamespace(rows_count=rows_count, artifacts=artifacts or {}, variables=variables or {})


# ──────────────────────────────────────────────
#  Arithmétique
# ──────────────────────────────────────────────

def test_addition_and_subtraction():
    assert evaluate("1 + 2", _ctx()) == 3
    assert evaluate("10 - 3", _ctx()) == 7


def test_multiplication_and_division():
    assert evaluate("4 * 5", _ctx()) == 20
    assert evaluate("10 / 4", _ctx()) == 2.5


def test_operator_precedence_additive_vs_multiplicative():
    assert evaluate("2 + 3 * 4", _ctx()) == 14
    assert evaluate("(2 + 3) * 4", _ctx()) == 20


def test_subtraction_with_named_operand():
    assert evaluate("rows_count - 5", _ctx(rows_count=12)) == 7


def test_unary_minus_on_identifier():
    assert evaluate("-rows_count", _ctx(rows_count=3)) == -3


def test_string_concatenation_via_plus():
    assert evaluate('"ab" + "cd"', _ctx()) == "abcd"


def test_multiplication_of_two_strings_raises_clean_error():
    with pytest.raises(ValueError):
        evaluate('"ab" * "cd"', _ctx())


def test_division_by_zero_raises_clean_error_not_zero_division_error():
    with pytest.raises(ValueError):
        evaluate("1 / 0", _ctx())


def test_bare_arithmetic_expression_is_valid_without_comparison():
    assert evaluate("rows_count + 1", _ctx(rows_count=4)) == 5


# ──────────────────────────────────────────────
#  Comparaisons et composition booléenne — comportement hérité préservé
# ──────────────────────────────────────────────

def test_comparison_still_works():
    assert evaluate("rows_count > 0", _ctx(rows_count=1)) is True
    assert evaluate("rows_count > 0", _ctx(rows_count=0)) is False


def test_and_or_not_composition():
    assert evaluate("rows_count > 0 and rows_count < 10", _ctx(rows_count=5)) is True
    assert evaluate("not (rows_count > 0)", _ctx(rows_count=0)) is True


def test_comparison_combined_with_arithmetic():
    assert evaluate("rows_count + 1 > 10", _ctx(rows_count=10)) is True
    assert evaluate("rows_count + 1 > 10", _ctx(rows_count=5)) is False


# ──────────────────────────────────────────────
#  Fonctions — cas nominal
# ──────────────────────────────────────────────

def test_date_add_default_format():
    assert evaluate('date_add("2026-01-10", -7)', _ctx()) == "2026-01-03"


def test_date_add_with_custom_format():
    assert evaluate('date_add("2026-01-10", 1, "{dd}/{MM}/{yyyy}")', _ctx()) == "11/01/2026"


def test_date_add_on_datetime_string():
    assert evaluate('date_add("2026-01-10T08:00:00", 1)', _ctx()) == "2026-01-11T08:00:00"


def test_now_and_today_return_strings():
    assert isinstance(evaluate("now()", _ctx()), str)
    assert isinstance(evaluate("today()", _ctx()), str)


def test_fmt_reformats_an_iso_date():
    assert evaluate('fmt("2026-01-10", "{dd}/{MM}/{yyyy}")', _ctx()) == "10/01/2026"


def test_concat_joins_any_number_of_values():
    assert evaluate('concat("a", "b", 1)', _ctx()) == "ab1"


def test_upper_and_lower():
    assert evaluate('upper("abc")', _ctx()) == "ABC"
    assert evaluate('lower("ABC")', _ctx()) == "abc"


def test_round_numeric():
    assert evaluate("round(3.14159, 2)", _ctx()) == 3.14


def test_nested_function_calls():
    assert evaluate('fmt(date_add(today(), 0), "{yyyy}")', _ctx()).isdigit()


def test_function_combined_with_variable():
    assert evaluate('date_add(var:date, -7)', _ctx(variables={"date": "2026-01-10"})) == "2026-01-03"


# ──────────────────────────────────────────────
#  Fonctions — erreurs d'arité détectées à la COMPILATION, sans ctx
# ──────────────────────────────────────────────

def test_unknown_function_is_a_compile_time_error():
    with pytest.raises(ValueError):
        compile_expression("nope(1)")


def test_wrong_arity_too_few_args_is_a_compile_time_error():
    with pytest.raises(ValueError):
        compile_expression("date_add(1)")


def test_wrong_arity_too_many_args_is_a_compile_time_error():
    with pytest.raises(ValueError):
        compile_expression("now(1)")


def test_concat_accepts_unbounded_args():
    compile_expression('concat("a", "b", "c", "d")')   # ne lève pas


def test_compile_expression_never_needs_a_real_context():
    # Preuve du découplage compile/eval exploité par dry_run_pipeline() : compiler une
    # expression référençant une variable/un artefact ne touche jamais ctx.
    node = compile_expression("var:pas_encore_connu + 1")
    assert node is not None


# ──────────────────────────────────────────────
#  Désambiguïsation moins unaire/binaire, artefacts/variables avec tiret
# ──────────────────────────────────────────────

def test_unquoted_artifact_name_with_hyphen_still_parses():
    ctx = _ctx(artifacts={"3f9a1c2b-step": "x.csv"})
    assert evaluate('artifact:3f9a1c2b-step != ""', ctx) is True


def test_date_add_with_negative_literal_argument():
    assert evaluate('date_add("2026-01-10", -1)', _ctx()) == "2026-01-09"


# ──────────────────────────────────────────────
#  Garde de récursion — parenthèses, not, ET appels de fonction imbriqués
# ──────────────────────────────────────────────

def test_deeply_nested_parentheses_raise_clean_error_not_recursion_error():
    expr = "(" * 100 + "rows_count > 0" + ")" * 100
    with pytest.raises(ValueError):
        compile_expression(expr)


def test_deeply_nested_function_calls_raise_clean_error_not_recursion_error():
    expr = "upper(" * 100 + '"a"' + ")" * 100
    with pytest.raises(ValueError):
        compile_expression(expr)


# ──────────────────────────────────────────────
#  Robustesse générale — jamais d'exception brute
# ──────────────────────────────────────────────

def test_empty_expression_raises_value_error():
    with pytest.raises(ValueError):
        compile_expression("")


def test_malformed_expression_raises_value_error():
    with pytest.raises(ValueError):
        compile_expression("rows_count >")


def test_no_eval_of_arbitrary_code():
    with pytest.raises(ValueError):
        evaluate("__import__('os').system('echo pwned')", _ctx())
