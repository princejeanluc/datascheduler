"""
DataScheduler — tests/test_step_context_fork.py
Vérifie StepContext.fork() (chantier parallélisme intra-pipeline, phase 1) — la copie isolée
utilisée par le futur moteur concurrent pour qu'aucune étape en cours dans un thread ne puisse
jamais affecter une autre étape concurrente avant que le coordinateur ne fusionne son résultat.
"""

from pathlib import Path

from core.steps.base import StepContext


def test_fork_artifacts_dict_is_independent_from_the_original():
    ctx = StepContext()
    ctx.artifacts["output_file"] = Path("a.csv")
    forked = ctx.fork()

    forked.artifacts["output_file"] = Path("b.csv")
    forked.artifacts["new_key"] = Path("c.csv")

    assert ctx.artifacts["output_file"] == Path("a.csv")   # jamais touché par la copie
    assert "new_key" not in ctx.artifacts


def test_fork_seeds_the_copy_with_everything_already_produced():
    ctx = StepContext()
    ctx.artifacts["step_a"] = Path("a.csv")
    ctx.artifacts["step_b"] = Path("b.csv")

    forked = ctx.fork()

    assert forked.artifacts == {"step_a": Path("a.csv"), "step_b": Path("b.csv")}
    assert forked.artifacts is not ctx.artifacts


def test_fork_log_lines_are_independent_and_start_empty():
    ctx = StepContext()
    ctx.log("déjà loggé avant la fourche")

    forked = ctx.fork()
    forked.log("loggé seulement sur la copie")

    assert len(forked.log_lines) == 1
    assert "loggé seulement sur la copie" in forked.log_lines[0]
    assert len(ctx.log_lines) == 1   # inchangé par l'écriture sur la copie


def test_fork_copies_rows_count_by_value():
    ctx = StepContext()
    ctx.rows_count = 42

    forked = ctx.fork()
    forked.rows_count = 100

    assert ctx.rows_count == 42


def test_fork_shares_extra_dict_by_reference():
    """extra est partagé à dessein (lu par resolve_tokens pour {error}/{failed_step}, jamais
    écrit par les steps eux-mêmes) — contrairement à artifacts, pas besoin d'isolation."""
    ctx = StepContext()
    ctx.extra["error_message"] = "un souci"

    forked = ctx.fork()

    assert forked.extra is ctx.extra


def test_fork_two_independent_copies_never_see_each_others_writes():
    """Simule ce que le moteur concurrent ferait pour deux branches indépendantes du même
    contexte partagé — chacune écrit son propre output_file sans jamais voir celui de l'autre."""
    shared = StepContext()
    shared.artifacts["parent"] = Path("parent.csv")

    branch_a = shared.fork()
    branch_b = shared.fork()

    branch_a.output_file = Path("a_result.csv")
    branch_b.output_file = Path("b_result.csv")

    assert branch_a.output_file == Path("a_result.csv")
    assert branch_b.output_file == Path("b_result.csv")
    assert shared.output_file is None   # le partagé n'a jamais été touché
