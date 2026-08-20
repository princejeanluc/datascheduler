"""
DataScheduler — tests/test_pipeline_graph_engine_parallel.py
Vérifie core.pipeline._execute_graph_parallel() (chantier parallélisme intra-pipeline, phase 2)
— appelée directement (pas encore branchée dans run_pipeline(), voir phase 3), avec des étapes/
arêtes réelles en base (db.save_pipeline_graph()/get_steps()/get_edges()), même patron que
tests/test_pipeline_graph_engine.py mais focalisé sur : (a) un vrai chevauchement temporel entre
branches indépendantes, (b) une parité de comportement métier avec _execute_graph (séquentiel),
(c) le respect du plafond de branches, (d) l'annulation.
"""

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import core.steps as steps_module
from core.pipeline import _execute_graph_parallel, run_pipeline, PipelineResult
from core.steps.base import BaseStep, StepResult
from database import db_manager as db


def _edge(from_key, to_key, from_port="output_file", to_port="input"):
    return {"from_step_key": from_key, "from_port": from_port, "to_step_key": to_key, "to_port": to_port}


def _run_parallel(pipeline_id, max_parallel_branches=4, skip_step_keys=frozenset(),
                   active_ports_seed=None, cancel_event=None):
    """Assemble ce que run_pipeline() ferait normalement (phase 3) et appelle
    _execute_graph_parallel() directement — steps/étapes réels depuis la base."""
    from core.steps.base import StepContext

    steps = db.get_steps(pipeline_id)
    edges = db.get_edges(pipeline_id)
    ctx = StepContext()
    result = PipelineResult()
    run = db.create_run(pipeline_id)
    result.run_id = run.id
    cancel_event = cancel_event or threading.Event()
    fake_pipeline = SimpleNamespace(max_parallel_branches=max_parallel_branches)

    outcome = _execute_graph_parallel(
        steps, edges, ctx, lambda *a: None, result, cancel_event, fake_pipeline,
        skip_step_keys=skip_step_keys, active_ports_seed=active_ports_seed or {},
    )
    return outcome, ctx, result


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


class _FakeDelayedStep(BaseStep):
    """Enregistre son propre intervalle [début, fin] dans un attribut de CLASSE (partagé entre
    threads, protégé par verrou) — prouve un vrai chevauchement temporel, pas juste "ça marche"."""
    PRODUCES = {"output_file"}
    timeline: list = []
    concurrent_count = 0
    max_concurrent_seen = 0
    lock = threading.Lock()

    def run(self, ctx, cancel_event=None, on_progress=None) -> StepResult:
        with _FakeDelayedStep.lock:
            _FakeDelayedStep.concurrent_count += 1
            _FakeDelayedStep.max_concurrent_seen = max(
                _FakeDelayedStep.max_concurrent_seen, _FakeDelayedStep.concurrent_count
            )
        start = time.monotonic()
        time.sleep(self.config.get("delay", 0.2))
        end = time.monotonic()
        with _FakeDelayedStep.lock:
            _FakeDelayedStep.timeline.append((self.config.get("label", "?"), start, end))
            _FakeDelayedStep.concurrent_count -= 1
        path = Path(self.config["path"])
        path.write_text("data")
        ctx.output_file = path
        return StepResult(success=True)


class _FakeBlockingStep(BaseStep):
    """Bloque jusqu'à ce que cancel_event soit positionné, puis coopère (comme un vrai step de
    ce chantier) — pour tester l'annulation sans dépendre d'un minuteur fragile."""

    def run(self, ctx, cancel_event=None, on_progress=None) -> StepResult:
        while cancel_event is not None and not cancel_event.is_set():
            time.sleep(0.02)
        return StepResult(success=False, error="annulé")


def _reset_fake_delayed_step():
    _FakeDelayedStep.timeline = []
    _FakeDelayedStep.concurrent_count = 0
    _FakeDelayedStep.max_concurrent_seen = 0


# ──────────────────────────────────────────────
#  Chevauchement temporel réel
# ──────────────────────────────────────────────

def test_two_independent_branches_run_with_real_time_overlap(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeDelayedStep)
    _reset_fake_delayed_step()

    pipeline = db.create_pipeline(name="parallel-overlap-test")
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a", "delay": 0.3, "label": "A",
                                                 "path": str(tmp_path / "a.txt")}},
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "b", "delay": 0.3, "label": "B",
                                                 "path": str(tmp_path / "b.txt")}},
    ], edges=[])   # aucune arête entre elles : deux branches indépendantes

    start = time.monotonic()
    (pipeline_failed, pipeline_cancelled, completed, _), ctx, result = _run_parallel(pipeline.id)
    total = time.monotonic() - start

    assert not pipeline_failed, result.error
    assert not pipeline_cancelled
    assert completed == {"a", "b"}
    assert total < 0.5   # bien moins que 0.3 + 0.3 = 0.6s si ça avait tourné en séquentiel

    assert len(_FakeDelayedStep.timeline) == 2
    (_, a_start, a_end), (_, b_start, b_end) = _FakeDelayedStep.timeline
    overlap = min(a_end, b_end) - max(a_start, b_start)
    assert overlap > 0, "les deux branches auraient dû se chevaucher dans le temps"


def test_max_parallel_branches_bounds_real_concurrency(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeDelayedStep)
    _reset_fake_delayed_step()

    pipeline = db.create_pipeline(name="parallel-bound-test")
    steps = [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": f"s{i}", "delay": 0.15, "label": f"S{i}",
                                                 "path": str(tmp_path / f"s{i}.txt")}}
        for i in range(6)
    ]
    db.save_pipeline_graph(pipeline.id, steps, edges=[])

    (pipeline_failed, _, completed, _), _, result = _run_parallel(pipeline.id, max_parallel_branches=2)

    assert not pipeline_failed, result.error
    assert len(completed) == 6
    assert _FakeDelayedStep.max_concurrent_seen <= 2


# ──────────────────────────────────────────────
#  Parité de comportement avec _execute_graph (séquentiel)
# ──────────────────────────────────────────────

def test_linear_chain_behaves_like_legacy_path(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)

    src, sink = tmp_path / "src.txt", tmp_path / "sink.txt"
    pipeline = db.create_pipeline(name="parallel-linear")
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "HELLO", "_step_key": "prod"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(sink), "_step_key": "cons"}},
    ], edges=[_edge("prod", "cons")])

    (pipeline_failed, pipeline_cancelled, completed, _), _, result = _run_parallel(pipeline.id)

    assert not pipeline_failed, result.error
    assert sink.read_text() == "HELLO"


def test_fan_out_failure_blocks_only_its_own_dependent(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeFailingStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)

    src, sink = tmp_path / "src.txt", tmp_path / "sink.txt"
    pipeline = db.create_pipeline(name="parallel-fanout")
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "DATA", "_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD", "config": {"_step_key": "fails"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(sink), "_step_key": "ok"}},
    ], edges=[_edge("prod", "fails"), _edge("prod", "ok")])

    (pipeline_failed, _, _, _), _, result = _run_parallel(pipeline.id)

    assert pipeline_failed
    assert sink.read_text() == "DATA"   # la branche indépendante a quand même tourné


def test_dependent_of_failed_step_is_skipped_not_failed_again(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeFailingStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)

    src = tmp_path / "src.txt"
    pipeline = db.create_pipeline(name="parallel-cascade")
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "DATA", "_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD", "config": {"_step_key": "fails"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(tmp_path / "never.txt"), "_step_key": "downstream"}},
    ], edges=[_edge("prod", "fails"), _edge("fails", "downstream")])

    (pipeline_failed, _, _, _), _, result = _run_parallel(pipeline.id)

    assert pipeline_failed
    assert not (tmp_path / "never.txt").exists()
    assert any("ignorée" in line for line in result.log_lines)


def test_run_always_step_executes_despite_failed_dependency(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeFailingStep)
    monkeypatch.setitem(steps_module._REGISTRY, "EMAIL_NOTIFY", _FakeConsumerStep)

    src, sink = tmp_path / "src.txt", tmp_path / "notify.txt"
    pipeline = db.create_pipeline(name="parallel-run-always")
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "DATA", "_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD", "config": {"_step_key": "fails"}},
        {"step_type": "EMAIL_NOTIFY", "config": {"sink_path": str(sink), "_step_key": "notify"},
         "run_always": True},
    ], edges=[_edge("prod", "fails"), _edge("fails", "notify")])

    (pipeline_failed, _, _, _), _, result = _run_parallel(pipeline.id)

    assert pipeline_failed
    assert sink.exists()


def test_condition_node_only_runs_the_selected_branch(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeConsumerStep)

    src = tmp_path / "src.txt"
    true_sink, false_sink = tmp_path / "true_branch.txt", tmp_path / "false_branch.txt"
    pipeline = db.create_pipeline(name="parallel-condition")
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

    (pipeline_failed, _, _, _), _, result = _run_parallel(pipeline.id)

    assert not pipeline_failed, result.error
    assert not true_sink.exists()   # rows_count > 0 est faux (aucune ligne comptée)
    assert false_sink.exists()


def test_cycle_prevents_any_execution(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)

    marker = tmp_path / "should_not_exist.txt"
    pipeline = db.create_pipeline(name="parallel-cycle")
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(tmp_path / "a.txt"), "_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(marker), "_step_key": "b"}},
    ], edges=[_edge("a", "b"), _edge("b", "a")])

    (pipeline_failed, _, _, _), _, result = _run_parallel(pipeline.id)

    assert pipeline_failed
    assert "cycle" in result.error
    assert not marker.exists()


def test_resume_skips_already_completed_steps(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)

    src, sink = tmp_path / "src.txt", tmp_path / "sink.txt"
    pipeline = db.create_pipeline(name="parallel-resume")
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "DATA", "_step_key": "prod"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(sink), "_step_key": "cons"}},
    ], edges=[_edge("prod", "cons")])

    # "prod" déjà réussi lors d'un run précédent — jamais réexécuté, mais son artefact doit être
    # réamorcé dans ctx.artifacts pour que "cons" (en aval) trouve sa source malgré tout.
    steps = db.get_steps(pipeline.id)
    edges = db.get_edges(pipeline.id)
    from core.steps.base import StepContext
    ctx = StepContext()
    ctx.artifacts["prod"] = src
    src.write_text("PRÉ-EXISTANT")
    result = PipelineResult()
    run = db.create_run(pipeline.id)
    result.run_id = run.id
    fake_pipeline = SimpleNamespace(max_parallel_branches=4)

    pipeline_failed, pipeline_cancelled, completed, _ = _execute_graph_parallel(
        steps, edges, ctx, lambda *a: None, result, threading.Event(), fake_pipeline,
        skip_step_keys=frozenset({"prod"}),
    )

    assert not pipeline_failed, result.error
    assert sink.read_text() == "PRÉ-EXISTANT"
    assert completed == {"prod", "cons"}


# ──────────────────────────────────────────────
#  Annulation coopérative (réutilisée telle quelle)
# ──────────────────────────────────────────────

def test_cancellation_stops_new_submissions_but_lets_in_flight_steps_finish(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeBlockingStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeProducerStep)

    pipeline = db.create_pipeline(name="parallel-cancel")
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "blocked"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "independent",
                                                 "path": str(tmp_path / "never_reached.txt")}},
    ], edges=[])   # deux branches indépendantes — la 2e ne doit jamais être soumise après annulation

    cancel_event = threading.Event()
    threading.Timer(0.1, cancel_event.set).start()

    (pipeline_failed, pipeline_cancelled, completed, _), _, result = _run_parallel(
        pipeline.id, max_parallel_branches=1, cancel_event=cancel_event,
    )

    assert pipeline_cancelled
    assert not pipeline_failed
    assert "interrompue par l'utilisateur" in result.error
    assert not (tmp_path / "never_reached.txt").exists()   # jamais soumise après l'annulation


# ──────────────────────────────────────────────
#  Aiguillage run_pipeline() (phase 3) — bout en bout
# ──────────────────────────────────────────────

def _fan_out_pipeline(name, parallel_execution_enabled, tmp_path, delay=0.2):
    """Un producteur rapide alimente deux branches lentes indépendantes — au moins une arête
    présente (déclenche le chemin graphe de run_pipeline(), `if edges:`), mais les deux branches
    en aval n'ont aucune dépendance entre elles : le cas réaliste où le parallélisme change
    vraiment le temps total, contrairement à deux nœuds totalement hors-graphe (edges=[]), que
    run_pipeline() traite comme un pipeline linéaire ordinaire (voir _execute_linear)."""
    pipeline = db.create_pipeline(
        name=name, parallel_execution_enabled=parallel_execution_enabled, max_parallel_branches=4,
    )
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "prod", "delay": 0, "label": "prod",
                                                 "path": str(tmp_path / "prod.txt")}},
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a", "delay": delay, "label": "A",
                                                 "path": str(tmp_path / "a.txt")}},
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "b", "delay": delay, "label": "B",
                                                 "path": str(tmp_path / "b.txt")}},
    ], edges=[_edge("prod", "a"), _edge("prod", "b")])
    return pipeline


def test_run_pipeline_uses_parallel_engine_when_pipeline_opted_in(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeDelayedStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeDelayedStep)
    _reset_fake_delayed_step()

    pipeline = _fan_out_pipeline("dispatch-parallel-test", True, tmp_path, delay=0.25)

    start = time.monotonic()
    result = run_pipeline(pipeline.id)
    elapsed = time.monotonic() - start

    assert result.success, result.error
    assert elapsed < 0.45   # bien moins que 0.25 + 0.25 = 0.5s si les deux branches s'enchaînaient


def test_run_pipeline_uses_sequential_graph_engine_by_default(test_db, monkeypatch, tmp_path):
    """parallel_execution_enabled=False (défaut) — même structure (un producteur, deux branches
    indépendantes), mais le chemin _execute_graph (séquentiel, inchangé) reste emprunté tant que
    l'utilisateur n'a pas explicitement activé le parallélisme pour CE pipeline."""
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeDelayedStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeDelayedStep)
    _reset_fake_delayed_step()

    pipeline = _fan_out_pipeline("dispatch-sequential-default-test", False, tmp_path, delay=0.2)

    start = time.monotonic()
    result = run_pipeline(pipeline.id)
    elapsed = time.monotonic() - start

    assert result.success, result.error
    assert elapsed >= 0.4   # 0.2 + 0.2 : les deux branches se sont bien enchaînées, pas chevauchées


def test_run_pipeline_ignores_parallel_flag_for_a_linear_pipeline_without_edges(test_db, monkeypatch, tmp_path):
    """parallel_execution_enabled=True mais aucune arête (pipeline jamais passé par l'éditeur
    graphique) — doit rester sur _execute_linear, inchangé ; le flag n'a de sens qu'en graphe."""
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)

    pipeline = db.create_pipeline(name="dispatch-linear-flag-noop-test", parallel_execution_enabled=True)
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(tmp_path / "a.txt"), "content": "X"}},
    ])

    result = run_pipeline(pipeline.id)

    assert result.success, result.error
