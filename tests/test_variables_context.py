"""
DataScheduler — tests/test_variables_context.py
ctx.variables (chantier EXTRACT_VARIABLES) : le token générique {var:nom} dans resolve_tokens()
(même convention que {artifact:nom}, voir tests/test_named_ports.py), et l'isolation par
StepContext.fork() (même convention que ctx.artifacts, voir tests/test_step_context_fork.py).
"""

from core.steps.base import StepContext


# ──────────────────────────────────────────────
#  resolve_tokens() — token générique {var:nom}
# ──────────────────────────────────────────────

def test_var_token_resolves_when_present():
    ctx = StepContext()
    ctx.variables["total"] = 1234.5
    assert ctx.resolve_tokens("Total : {var:total} €") == "Total : 1234.5 €"


def test_var_token_stays_literal_when_absent():
    ctx = StepContext()
    assert ctx.resolve_tokens("{var:inconnu}") == "{var:inconnu}"


def test_var_token_coexists_with_artifact_and_date_tokens():
    ctx = StepContext()
    ctx.artifacts["ventes_csv"] = "/tmp/ventes.csv"
    ctx.variables["total"] = 42
    result = ctx.resolve_tokens("{artifact:ventes_csv} — total {var:total}")
    assert result == "/tmp/ventes.csv — total 42"


# ──────────────────────────────────────────────
#  fork() — isolation, même patron que ctx.artifacts
# ──────────────────────────────────────────────

def test_fork_variables_dict_is_independent_from_the_original():
    ctx = StepContext()
    ctx.variables["a"] = 1
    forked = ctx.fork()
    forked.variables["b"] = 2
    assert "b" not in ctx.variables


def test_fork_seeds_the_copy_with_everything_already_extracted():
    ctx = StepContext()
    ctx.variables["a"] = 1
    forked = ctx.fork()
    assert forked.variables == {"a": 1}
