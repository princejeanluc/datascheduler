"""
DataScheduler — tests/test_gateway_join_step.py
GatewayJoinStep + get_join_mode() (chantier Gateway) : la classe elle-même ne gère QUE la
désignation d'artefact (config "artifact_source_step_key") — la sémantique ET/OU vit dans le
moteur (core/pipeline.py), pilotée par get_join_mode(), testée ici en pur. Les scénarios
d'exécution complets (2+ branches réelles convergeant) sont dans
tests/test_pipeline_graph_engine.py et son pendant parallèle.
"""

from core.steps import get_step, get_join_mode, step_produces_output_file
from core.steps.base import StepContext


# ──────────────────────────────────────────────
#  get_join_mode()
# ──────────────────────────────────────────────

def test_get_join_mode_none_for_non_join_types():
    assert get_join_mode("DB_EXTRACT", {}) is None
    assert get_join_mode("CONDITION", {}) is None
    assert get_join_mode("GATEWAY_PARALLEL", {}) is None


def test_get_join_mode_defaults_to_or():
    assert get_join_mode("GATEWAY_JOIN", {}) == "OR"


def test_get_join_mode_respects_explicit_config():
    assert get_join_mode("GATEWAY_JOIN", {"join_mode": "AND"}) == "AND"
    assert get_join_mode("GATEWAY_JOIN", {"join_mode": "OR"}) == "OR"


def test_get_join_mode_unknown_type_is_none():
    assert get_join_mode("NOT_A_REAL_TYPE", {}) is None


# ──────────────────────────────────────────────
#  GatewayJoinStep.run() — désignation d'artefact uniquement
# ──────────────────────────────────────────────

def test_run_forwards_designated_branch_artifact():
    ctx = StepContext()
    ctx.artifacts["branch_a"] = "/tmp/a.csv"
    ctx.artifacts["branch_b"] = "/tmp/b.csv"

    result = get_step("GATEWAY_JOIN", {"artifact_source_step_key": "branch_b"}).run(ctx)

    assert result.success
    assert ctx.output_file == "/tmp/b.csv"


def test_run_without_designation_clears_output_file():
    ctx = StepContext()
    ctx.artifacts["branch_a"] = "/tmp/a.csv"
    ctx.output_file = "/tmp/stale_leftover.csv"   # simule un reliquat de ctx.fork()

    result = get_step("GATEWAY_JOIN", {}).run(ctx)

    assert result.success
    assert ctx.output_file is None


def test_run_designated_branch_never_ran_logs_warning_and_clears():
    ctx = StepContext()
    result = get_step("GATEWAY_JOIN", {"artifact_source_step_key": "never_ran"}).run(ctx)
    assert result.success
    assert ctx.output_file is None
    assert any("n'a pas produit d'artefact" in line for line in ctx.log_lines)


# ──────────────────────────────────────────────
#  step_produces_output_file — config-dépendant, comme SPARK_SQL
# ──────────────────────────────────────────────

def test_produces_output_file_only_when_source_designated():
    assert step_produces_output_file("GATEWAY_JOIN", {}) is False
    assert step_produces_output_file("GATEWAY_JOIN", {"artifact_source_step_key": ""}) is False
    assert step_produces_output_file("GATEWAY_JOIN", {"artifact_source_step_key": "x"}) is True
