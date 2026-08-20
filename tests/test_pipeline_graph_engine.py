"""
DataScheduler — tests/test_pipeline_graph_engine.py
Moteur d'exécution DAG (chantier 6a) : ordre topologique, échec = blocage local seulement
(les branches indépendantes continuent), branchement conditionnel via ConditionStep, détection
de cycle. Même patron que tests/test_step_context_artifacts.py (chantier 3) : steps factices
substitués dans le registre, fixture test_db, round-trip complet via run_pipeline().
"""

from pathlib import Path

import core.steps as steps_module
from core.pipeline import validate_pipeline_graph, run_pipeline
from core.steps.base import BaseStep, StepResult
from database import db_manager as db


class _FakeProducerStep(BaseStep):
    PRODUCES = {"output_file"}

    def run(self, ctx, cancel_event=None, on_progress=None) -> StepResult:
        path = Path(self.config["path"])
        path.write_text(self.config.get("content", ""))
        ctx.output_file = path
        return StepResult(success=True)


class _FakeFailingStep(BaseStep):
    REQUIRES = {"output_file"}

    def run(self, ctx, cancel_event=None, on_progress=None) -> StepResult:
        return StepResult(success=False, error="échec simulé")


class _FakeConsumerStep(BaseStep):
    """Pas de PRODUCES délibérément : un vrai step terminal (FTP_UPLOAD/LOCAL_COPY réels) ne
    republie rien dans ctx.artifacts — ce qui, comme ici, évite que son fichier de sortie soit
    balayé par le nettoyage des temporaires en fin de run_pipeline (voir core/pipeline.py)."""
    REQUIRES = {"output_file"}

    def run(self, ctx, cancel_event=None, on_progress=None) -> StepResult:
        sink = Path(self.config["sink_path"])
        sink.write_text(ctx.output_file.read_text() if ctx.output_file else "")
        return StepResult(success=True)


def _edge(from_key, to_key, from_port="output_file", to_port="input"):
    return {"from_step_key": from_key, "from_port": from_port, "to_step_key": to_key, "to_port": to_port}


# ──────────────────────────────────────────────
#  validate_pipeline_graph — dicts en mémoire, pas de DB
# ──────────────────────────────────────────────

def test_validate_accepts_valid_linear_graph():
    steps = [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "DB_LOAD", "config": {"_step_key": "b"}},
    ]
    edges = [_edge("a", "b")]
    errors, warnings = validate_pipeline_graph(steps, edges)
    assert errors == []
    assert warnings == []


def test_validate_flags_missing_incoming_edge_for_required_step():
    steps = [{"step_type": "DB_LOAD", "config": {"_step_key": "b"}}]
    errors, _ = validate_pipeline_graph(steps, edges=[])
    assert len(errors) == 1
    assert "aucune arête entrante" in errors[0]


def test_validate_missing_edge_becomes_warning_when_run_always():
    steps = [{"step_type": "DB_LOAD", "config": {"_step_key": "b"}, "run_always": True}]
    errors, warnings = validate_pipeline_graph(steps, edges=[])
    assert errors == []
    assert len(warnings) == 1


def test_validate_detects_cycle():
    steps = [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "DB_LOAD", "config": {"_step_key": "b"}},
    ]
    edges = [_edge("a", "b"), _edge("b", "a")]
    errors, _ = validate_pipeline_graph(steps, edges)
    assert len(errors) == 1
    assert "cycle" in errors[0]


# ──────────────────────────────────────────────
#  Exécuteur de bout en bout — steps factices substitués dans le registre
# ──────────────────────────────────────────────

def test_linear_chain_behaves_like_legacy_path(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)

    src  = tmp_path / "src.txt"
    sink = tmp_path / "sink.txt"

    pipeline = db.create_pipeline(name="graph-linear")
    steps = [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "HELLO", "_step_key": "prod"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(sink), "_step_key": "cons"}},
    ]
    edges = [_edge("prod", "cons")]
    db.save_pipeline_graph(pipeline.id, steps, edges)

    result = run_pipeline(pipeline.id)

    assert result.success, result.error
    assert sink.read_text() == "HELLO"


def test_fan_out_failure_blocks_only_its_own_dependent(test_db, monkeypatch, tmp_path):
    """Un producteur alimente deux branches indépendantes : l'une échoue, l'autre doit quand
    même s'exécuter jusqu'au bout — c'est le bénéfice de résilience du DAG."""
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeFailingStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)

    src  = tmp_path / "src.txt"
    sink = tmp_path / "sink.txt"

    pipeline = db.create_pipeline(name="graph-fanout")
    steps = [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "DATA", "_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD", "config": {"_step_key": "fails"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(sink), "_step_key": "ok"}},
    ]
    edges = [_edge("prod", "fails"), _edge("prod", "ok")]
    db.save_pipeline_graph(pipeline.id, steps, edges)

    result = run_pipeline(pipeline.id)

    assert not result.success   # au moins une étape a échoué
    assert sink.read_text() == "DATA"   # mais la branche indépendante a bien tourné


def test_dependent_of_failed_step_is_skipped_not_failed_again(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeFailingStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)

    src = tmp_path / "src.txt"

    pipeline = db.create_pipeline(name="graph-cascade")
    steps = [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "DATA", "_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD", "config": {"_step_key": "fails"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(tmp_path / "never.txt"), "_step_key": "downstream"}},
    ]
    edges = [_edge("prod", "fails"), _edge("fails", "downstream")]
    db.save_pipeline_graph(pipeline.id, steps, edges)

    result = run_pipeline(pipeline.id)

    assert not result.success
    assert not (tmp_path / "never.txt").exists()
    assert any("ignorée" in line for line in result.log_lines)


def test_run_always_step_executes_despite_failed_dependency(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeFailingStep)
    monkeypatch.setitem(steps_module._REGISTRY, "EMAIL_NOTIFY", _FakeConsumerStep)

    src  = tmp_path / "src.txt"
    sink = tmp_path / "notify.txt"

    pipeline = db.create_pipeline(name="graph-run-always")
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "DATA", "_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD", "config": {"_step_key": "fails"}},
        {"step_type": "EMAIL_NOTIFY", "config": {"sink_path": str(sink), "_step_key": "notify"},
         "run_always": True},
    ], edges=[_edge("prod", "fails"), _edge("fails", "notify")])

    result = run_pipeline(pipeline.id)

    assert not result.success
    assert sink.exists()   # exécutée quand même malgré la dépendance en échec


def test_condition_node_only_runs_the_selected_branch(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeConsumerStep)

    src        = tmp_path / "src.txt"
    true_sink  = tmp_path / "true_branch.txt"
    false_sink = tmp_path / "false_branch.txt"

    pipeline = db.create_pipeline(name="graph-condition")
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "DATA", "_step_key": "prod"}},
        {"step_type": "CONDITION", "config": {"expression": "rows_count > 0", "_step_key": "cond"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(true_sink), "_step_key": "on_true"}},
        {"step_type": "FTP_UPLOAD", "config": {"sink_path": str(false_sink), "_step_key": "on_false"}},
    ], edges=[
        _edge("prod", "cond"),
        _edge("cond", "on_true", from_port="true"),
        _edge("cond", "on_false", from_port="false"),
    ])

    result = run_pipeline(pipeline.id)

    assert result.success, result.error
    assert not true_sink.exists()     # rows_count > 0 est faux (aucune ligne n'a été comptée)
    assert false_sink.exists()
    assert any("ignorée" in line for line in result.log_lines)


def test_cycle_prevents_any_execution(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)

    marker = tmp_path / "should_not_exist.txt"
    pipeline = db.create_pipeline(name="graph-cycle")
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(tmp_path / "a.txt"), "_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(marker), "_step_key": "b"}},
    ], edges=[_edge("a", "b"), _edge("b", "a")])

    result = run_pipeline(pipeline.id)

    assert not result.success
    assert "cycle" in result.error
    assert not marker.exists()
