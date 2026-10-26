"""
DataScheduler — tests/test_pipeline_run_steps.py
B1 (DONNEES.md::D1, fiche Atelier) : une ligne `pipeline_run_steps` par étape exécutée ou sautée,
écrite par core/pipeline.py autour de _run_step_with_policy, dans les 3 moteurs d'exécution
(linéaire, graphe séquentiel, graphe parallèle) et lors d'une reprise. Même patron de steps
factices substitués dans le registre que tests/test_pipeline_graph_engine.py.
"""

import json
from pathlib import Path

import core.steps as steps_module
from core.pipeline import run_pipeline
from core.steps.base import BaseStep, StepResult
from database import db_manager as db
from database.models import PipelineRunStep


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
    REQUIRES = {"output_file"}

    def run(self, ctx, cancel_event=None, on_progress=None) -> StepResult:
        sink = Path(self.config["sink_path"])
        sink.write_text(ctx.output_file.read_text() if ctx.output_file else "")
        return StepResult(success=True)


def _edge(from_key, to_key, from_port="output_file", to_port="input"):
    return {"from_step_key": from_key, "from_port": from_port, "to_step_key": to_key, "to_port": to_port}


def _run_steps(run_id: int) -> list[PipelineRunStep]:
    with db.get_session() as s:
        rows = s.query(PipelineRunStep).filter(PipelineRunStep.run_id == run_id).all()
        s.expunge_all()
    return rows


# ──────────────────────────────────────────────
#  Migration (une base 0.45.0 n'a pas cette table du tout — table neuve, pas une colonne)
# ──────────────────────────────────────────────

def test_a_045_style_database_gets_the_new_table_created(tmp_path):
    from sqlalchemy import create_engine, text

    db_path = tmp_path / "legacy_045.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        # pipeline_runs "legacy" (sans les colonnes des chantiers ultérieurs) — pipeline_run_steps
        # n'existe pas du tout, comme dans toute base 0.45.0.
        conn.execute(text(
            "CREATE TABLE pipeline_runs (id INTEGER PRIMARY KEY, pipeline_id INTEGER, "
            "started_at DATETIME, finished_at DATETIME, status VARCHAR(20), "
            "rows_exported INTEGER, remote_path VARCHAR(500), error_message TEXT, log_text TEXT)"
        ))
        conn.commit()
    engine.dispose()

    db.init_db(db_path)
    tables = {r[0] for r in create_engine(f"sqlite:///{db_path}").connect()
              .execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()}
    assert "pipeline_run_steps" in tables

    db._engine = None
    db._SessionFactory = None


# ──────────────────────────────────────────────
#  Moteur linéaire
# ──────────────────────────────────────────────

def test_linear_run_writes_one_row_per_executed_step(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)

    src, sink = tmp_path / "src.txt", tmp_path / "sink.txt"
    pipeline = db.create_pipeline(name="run-steps-linear")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "A", "_step_key": "prod"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(sink), "_step_key": "cons"}},
    ])

    result = run_pipeline(pipeline.id)
    assert result.success, result.error

    rows = _run_steps(result.run_id)
    assert len(rows) == 2
    by_key = {r.step_key: r for r in rows}
    assert by_key["prod"].status == "SUCCESS"
    assert by_key["cons"].status == "SUCCESS"
    assert by_key["prod"].attempts == 1
    assert by_key["prod"].started_at is not None
    assert by_key["prod"].finished_at is not None
    assert json.loads(by_key["prod"].attempts_json)[0]["n"] == 1


def test_linear_run_records_retry_attempts(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)

    class _SucceedsOnSecondCall(BaseStep):
        attempt = 0

        def run(self, ctx, cancel_event=None, on_progress=None):
            _SucceedsOnSecondCall.attempt += 1
            if _SucceedsOnSecondCall.attempt < 2:
                return StepResult(success=False, error="échec transitoire")
            return StepResult(success=True)

    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _SucceedsOnSecondCall)

    pipeline = db.create_pipeline(name="run-steps-retry")
    db.save_steps(pipeline.id, [
        {"step_type": "FTP_UPLOAD", "config": {"_step_key": "flaky"},
         "retry_count": 2, "retry_interval_s": 0},
    ])

    result = run_pipeline(pipeline.id)
    assert result.success, result.error

    rows = _run_steps(result.run_id)
    assert len(rows) == 1
    assert rows[0].attempts == 2
    attempts = json.loads(rows[0].attempts_json)
    assert len(attempts) == 2
    assert attempts[0]["error"] == "échec transitoire"
    assert attempts[1]["error"] is None


def test_linear_run_records_failed_step_with_error_message(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeFailingStep)

    pipeline = db.create_pipeline(name="run-steps-linear-fail")
    db.save_steps(pipeline.id, [
        {"step_type": "FTP_UPLOAD", "config": {"_step_key": "fails"}},
    ])

    result = run_pipeline(pipeline.id)
    assert not result.success

    rows = _run_steps(result.run_id)
    assert len(rows) == 1
    assert rows[0].status == "FAILED"
    assert rows[0].error_message == "échec simulé"


# ──────────────────────────────────────────────
#  Moteur graphe (séquentiel) — branche non sélectionnée = SKIPPED
# ──────────────────────────────────────────────

def test_graph_run_marks_the_unselected_branch_of_a_condition_as_skipped(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)

    class _TrueCondition(BaseStep):
        def run(self, ctx, cancel_event=None, on_progress=None):
            return StepResult(success=True, active_port="true")

    monkeypatch.setitem(steps_module._REGISTRY, "CONDITION", _TrueCondition)

    src = tmp_path / "src.txt"
    sink_true, sink_false = tmp_path / "t.txt", tmp_path / "f.txt"
    pipeline = db.create_pipeline(name="run-steps-condition")
    steps = [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "A", "_step_key": "prod"}},
        {"step_type": "CONDITION",  "config": {"_step_key": "cond", "expression": "1 == 1"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(sink_true), "_step_key": "on_true"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(sink_false), "_step_key": "on_false"}},
    ]
    edges = [
        _edge("prod", "cond"),
        _edge("cond", "on_true", from_port="true"),
        _edge("cond", "on_false", from_port="false"),
    ]
    db.save_pipeline_graph(pipeline.id, steps, edges)

    result = run_pipeline(pipeline.id)
    assert result.success, result.error

    rows = _run_steps(result.run_id)
    by_key = {r.step_key: r for r in rows}
    assert by_key["on_true"].status == "SUCCESS"
    assert by_key["on_false"].status == "SKIPPED"
    assert by_key["cond"].port_taken == "true"


# ──────────────────────────────────────────────
#  Moteur graphe parallèle
# ──────────────────────────────────────────────

def test_parallel_run_writes_a_row_for_each_branch(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeConsumerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)

    src = tmp_path / "src.txt"
    sink_a, sink_b = tmp_path / "a.txt", tmp_path / "b.txt"
    pipeline = db.create_pipeline(
        name="run-steps-parallel", parallel_execution_enabled=True, max_parallel_branches=4,
    )
    steps = [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "A", "_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD", "config": {"sink_path": str(sink_a), "_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(sink_b), "_step_key": "b"}},
    ]
    edges = [_edge("prod", "a"), _edge("prod", "b")]
    db.save_pipeline_graph(pipeline.id, steps, edges)

    result = run_pipeline(pipeline.id)
    assert result.success, result.error

    rows = _run_steps(result.run_id)
    by_key = {r.step_key: r for r in rows}
    assert set(by_key) == {"prod", "a", "b"}
    assert all(r.status == "SUCCESS" for r in rows)


# ──────────────────────────────────────────────
#  Reprise (chantier J.2) — reused_from_resume
# ──────────────────────────────────────────────

def test_resume_marks_the_reused_step_as_skipped_resume(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)

    class _SucceedsOnSecondCall(BaseStep):
        attempt = 0

        def run(self, ctx, cancel_event=None, on_progress=None):
            _SucceedsOnSecondCall.attempt += 1
            if _SucceedsOnSecondCall.attempt < 2:
                return StepResult(success=False, error="échec simulé (1re tentative)")
            return StepResult(success=True)

    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _SucceedsOnSecondCall)

    p1 = tmp_path / "p1.txt"
    pipeline = db.create_pipeline(name="run-steps-resume")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(p1), "content": "A", "_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD", "config": {"_step_key": "fail"}},
    ])

    first = run_pipeline(pipeline.id)
    assert not first.success

    resumable = db.get_last_resumable_run(pipeline.id)
    second = run_pipeline(pipeline.id, resume_from_run_id=resumable.id)
    assert second.success, second.error

    rows = _run_steps(second.run_id)
    by_key = {r.step_key: r for r in rows}
    assert by_key["prod"].status == "SKIPPED_RESUME"
    assert by_key["prod"].reused_from_resume is True
    assert by_key["fail"].status == "SUCCESS"
    assert by_key["fail"].reused_from_resume is False


# ──────────────────────────────────────────────
#  Suppression en cascade
# ──────────────────────────────────────────────

def test_deleting_a_pipeline_cascades_to_its_run_steps(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)

    pipeline = db.create_pipeline(name="run-steps-cascade")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(tmp_path / "x.txt"), "content": "A", "_step_key": "a"}},
    ])
    result = run_pipeline(pipeline.id)
    assert result.success, result.error
    assert len(_run_steps(result.run_id)) == 1

    db.delete_pipeline(pipeline.id)

    with db.get_session() as s:
        remaining = s.query(PipelineRunStep).filter(PipelineRunStep.run_id == result.run_id).count()
    assert remaining == 0


# ──────────────────────────────────────────────
#  Lecture (C9, Atelier-echec) — jusqu'ici personne ne lisait cette table
# ──────────────────────────────────────────────

def test_get_run_steps_returns_every_row_for_that_run_in_insertion_order(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)

    pipeline = db.create_pipeline(name="run-steps-read")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(tmp_path / "x.txt"), "content": "A", "_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(tmp_path / "y.txt"), "_step_key": "b"}},
    ])
    result = run_pipeline(pipeline.id)
    assert result.success, result.error

    rows = db.get_run_steps(result.run_id)

    assert [r.step_key for r in rows] == ["a", "b"]
    assert all(r.status == "SUCCESS" for r in rows)


def test_get_run_steps_is_scoped_to_a_single_run(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)

    pipeline = db.create_pipeline(name="run-steps-scoped")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(tmp_path / "x.txt"), "content": "A", "_step_key": "a"}},
    ])
    first = run_pipeline(pipeline.id)
    second = run_pipeline(pipeline.id)

    assert [r.run_id for r in db.get_run_steps(first.run_id)] == [first.run_id]
    assert [r.run_id for r in db.get_run_steps(second.run_id)] == [second.run_id]


def test_get_run_steps_empty_for_an_unknown_run(test_db):
    assert db.get_run_steps(999999) == []
