"""
DataScheduler — tests/test_pipeline_graph_engine.py
Moteur d'exécution DAG (chantier 6a) : ordre topologique, échec = blocage local seulement
(les branches indépendantes continuent), branchement conditionnel via ConditionStep, détection
de cycle. Même patron que tests/test_step_context_artifacts.py (chantier 3) : steps factices
substitués dans le registre, fixture test_db, round-trip complet via run_pipeline().
"""

from pathlib import Path

import core.steps as steps_module
from core.pipeline import validate_pipeline_graph, run_pipeline, topological_ranks
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
#  validate_pipeline_graph — port d'erreur générique
# ──────────────────────────────────────────────

def test_validate_error_port_edge_alone_does_not_satisfy_requires():
    """Un gestionnaire d'erreur alimenté SEULEMENT par le port "error" d'une étape amont ne
    reçoit généralement aucune donnée réelle — ça ne doit pas satisfaire son REQUIRES."""
    steps = [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "DB_LOAD", "config": {"_step_key": "b"}},
    ]
    edges = [_edge("a", "b", from_port="error")]
    errors, _ = validate_pipeline_graph(steps, edges)
    assert len(errors) == 1
    assert "aucune arête entrante" in errors[0]


def test_validate_error_port_edge_alongside_a_normal_edge_still_satisfies_requires():
    """La même étape, alimentée EN PLUS par une arête normale, reste valide — l'arête "error"
    ne retire rien, elle ne compte simplement pas comme suffisante à elle seule."""
    steps = [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a2"}},
        {"step_type": "DB_LOAD", "config": {"_step_key": "b"}},
    ]
    edges = [_edge("a", "b"), _edge("a2", "b", from_port="error")]
    errors, warnings = validate_pipeline_graph(steps, edges)
    assert errors == []
    assert warnings == []


def test_topological_ranks_linear_chain():
    ranks = topological_ranks(["a", "b", "c"], [_edge("a", "b"), _edge("b", "c")])
    assert ranks == {"a": 0, "b": 1, "c": 2}


def test_topological_ranks_disconnected_nodes_all_get_rank_zero():
    ranks = topological_ranks(["a", "b", "c"], [])
    assert ranks == {"a": 0, "b": 0, "c": 0}


def test_topological_ranks_diamond_takes_the_longer_path():
    # a -> b -> d, a -> c -> d : d doit être au rang max(rang(b), rang(c)) + 1, pas juste après
    # le premier chemin trouvé.
    ranks = topological_ranks(
        ["a", "b", "c", "d"],
        [_edge("a", "b"), _edge("a", "c"), _edge("b", "d"), _edge("c", "d")],
    )
    assert ranks == {"a": 0, "b": 1, "c": 1, "d": 2}


def test_topological_ranks_returns_none_on_cycle():
    assert topological_ranks(["a", "b"], [_edge("a", "b"), _edge("b", "a")]) is None


def test_topological_ranks_ignores_edges_referencing_unknown_keys():
    """Une arête pointant vers une clé absente de step_keys (nœud supprimé entre-temps, ou
    filtre volontaire) est ignorée plutôt que de faire planter le calcul."""
    ranks = topological_ranks(["a", "b"], [_edge("a", "b"), _edge("b", "ghost")])
    assert ranks == {"a": 0, "b": 1}


def test_validate_detects_cycle_formed_purely_via_error_port_edges():
    """La détection de cycle utilise les arêtes NON filtrées — un cycle formé uniquement via
    des arêtes "error" doit rester détecté, l'exclusion ne s'applique qu'au test REQUIRES."""
    steps = [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "b"}},
    ]
    edges = [_edge("a", "b", from_port="error"), _edge("b", "a", from_port="error")]
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


# ──────────────────────────────────────────────
#  GATEWAY_PARALLEL (chantier Gateway) — fork explicite, chaque branche doit recevoir
#  l'artefact amont (non-régression directe du Bug 1 trouvé en recherche : un run() no-op
#  laisserait chaque branche recevoir None).
# ──────────────────────────────────────────────

def test_gateway_parallel_forwards_artifact_to_every_branch(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeConsumerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)

    src = tmp_path / "src.txt"
    sink_a, sink_b = tmp_path / "sink_a.txt", tmp_path / "sink_b.txt"
    pipeline = db.create_pipeline(name="graph-gateway-parallel")
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "DATA", "_step_key": "prod"}},
        {"step_type": "GATEWAY_PARALLEL", "config": {"_step_key": "gw"}},
        {"step_type": "FTP_UPLOAD", "config": {"sink_path": str(sink_a), "_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(sink_b), "_step_key": "b"}},
    ], edges=[_edge("prod", "gw"), _edge("gw", "a"), _edge("gw", "b")])

    result = run_pipeline(pipeline.id)

    assert result.success, result.error
    assert sink_a.read_text() == "DATA"
    assert sink_b.read_text() == "DATA"


# ──────────────────────────────────────────────
#  failed_step_key (chantier UX éditeur, Lot 1, B1) — survit après la fin du run, contrairement
#  à current_step_key, pour un lien "Voir dans le graphe" depuis l'historique.
# ──────────────────────────────────────────────

def test_failed_step_key_recorded_for_linear_pipeline_failure(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeFailingStep)

    pipeline = db.create_pipeline(name="linear-failed-step-key")
    db.save_steps(pipeline.id, [
        {"step_type": "FTP_UPLOAD", "config": {"_step_key": "fails"}},
    ])

    result = run_pipeline(pipeline.id)

    assert not result.success
    assert result.failed_step_key == "fails"
    run = db.get_run(result.run_id)
    assert run.failed_step_key == "fails"


def test_failed_step_key_recorded_for_graph_pipeline_failure(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeFailingStep)

    src = tmp_path / "src.txt"
    pipeline = db.create_pipeline(name="graph-failed-step-key")
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "DATA", "_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD", "config": {"_step_key": "fails"}},
    ], edges=[_edge("prod", "fails")])

    result = run_pipeline(pipeline.id)

    assert not result.success
    assert result.failed_step_key == "fails"
    run = db.get_run(result.run_id)
    assert run.failed_step_key == "fails"


def test_failed_step_key_is_none_for_a_successful_run(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)

    src, sink = tmp_path / "src.txt", tmp_path / "sink.txt"
    pipeline = db.create_pipeline(name="success-no-failed-step-key")
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "DATA", "_step_key": "prod"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(sink), "_step_key": "ok"}},
    ], edges=[_edge("prod", "ok")])

    result = run_pipeline(pipeline.id)

    assert result.success
    assert result.failed_step_key is None
    run = db.get_run(result.run_id)
    assert run.failed_step_key is None


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


# ──────────────────────────────────────────────
#  Port d'erreur générique (analogue BPMN "événement-frontière d'erreur")
# ──────────────────────────────────────────────

def test_step_failure_routes_via_its_error_port_while_normal_port_is_skipped(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeFailingStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "EMAIL_NOTIFY", _FakeConsumerStep)

    src         = tmp_path / "src.txt"
    normal_sink = tmp_path / "never.txt"
    error_sink  = tmp_path / "handled.txt"

    pipeline = db.create_pipeline(name="graph-error-port")
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "DATA", "_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD", "config": {"_step_key": "fails"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(normal_sink), "_step_key": "downstream"}},
        {"step_type": "EMAIL_NOTIFY", "config": {"sink_path": str(error_sink), "_step_key": "handler"}},
    ], edges=[
        _edge("prod", "fails"),
        _edge("fails", "downstream"),                    # port normal — ignorée sur échec
        _edge("fails", "handler", from_port="error"),     # port erreur — s'exécute sur échec
    ])

    result = run_pipeline(pipeline.id)

    assert not result.success
    assert not normal_sink.exists()
    assert error_sink.exists()


def test_run_always_step_executes_even_when_only_edge_is_an_unfired_error_port(test_db, monkeypatch, tmp_path):
    """run_always et le port d'erreur sont deux mécanismes indépendants : un step run_always
    s'exécute même si sa SEULE arête entrante est un port "error" jamais déclenché (source
    réussie, donc ce port reste indisponible) — run_always ignore la disponibilité des arêtes,
    un point déjà vrai avant ce chantier, toujours vrai après."""
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "EMAIL_NOTIFY", _FakeConsumerStep)

    src  = tmp_path / "src.txt"
    sink = tmp_path / "notify.txt"

    pipeline = db.create_pipeline(name="graph-run-always-error-port")
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "DATA", "_step_key": "prod"}},
        {"step_type": "EMAIL_NOTIFY", "config": {"sink_path": str(sink), "_step_key": "notify"},
         "run_always": True},
    ], edges=[_edge("prod", "notify", from_port="error")])

    result = run_pipeline(pipeline.id)

    assert result.success, result.error
    assert sink.exists()


def test_condition_step_failure_routes_via_error_port(test_db, monkeypatch, tmp_path):
    """ConditionStep laisse active_port=None sur échec (expression invalide) — le backfill
    générique du moteur le comble à "error", exactement comme pour n'importe quel autre type
    d'étape en échec."""
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "EMAIL_NOTIFY", _FakeConsumerStep)

    src  = tmp_path / "src.txt"
    sink = tmp_path / "on_error.txt"

    pipeline = db.create_pipeline(name="graph-condition-error")
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "DATA", "_step_key": "prod"}},
        {"step_type": "CONDITION", "config": {"expression": "n'importe quoi d'invalide", "_step_key": "cond"}},
        {"step_type": "EMAIL_NOTIFY", "config": {"sink_path": str(sink), "_step_key": "handler"}},
    ], edges=[
        _edge("prod", "cond"),
        _edge("cond", "handler", from_port="error"),
    ])

    result = run_pipeline(pipeline.id)

    assert not result.success
    assert sink.exists()


def test_downstream_of_error_handler_routes_from_handlers_own_success_port(test_db, monkeypatch, tmp_path):
    """Le port d'erreur ne se propage pas au-delà d'un saut : une étape en aval d'un
    gestionnaire d'erreur route normalement depuis le port de succès de CE gestionnaire, sans
    lien avec l'échec d'origine plus haut dans le graphe."""
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeFailingStep)
    monkeypatch.setitem(steps_module._REGISTRY, "EMAIL_NOTIFY", _FakeConsumerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)

    src          = tmp_path / "src.txt"
    handled_sink = tmp_path / "handled.txt"
    after_sink   = tmp_path / "after_handler.txt"

    pipeline = db.create_pipeline(name="graph-error-one-hop")
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(src), "content": "DATA", "_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD", "config": {"_step_key": "fails"}},
        {"step_type": "EMAIL_NOTIFY", "config": {"sink_path": str(handled_sink), "_step_key": "handler"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(after_sink), "_step_key": "after"}},
    ], edges=[
        _edge("prod", "fails"),
        _edge("fails", "handler", from_port="error"),
        _edge("handler", "after"),   # port normal depuis "handler", qui a réussi
    ])

    result = run_pipeline(pipeline.id)

    assert not result.success   # le pipeline reste en échec (fails a vraiment échoué)
    assert handled_sink.exists()
    assert after_sink.exists()  # la propagation d'erreur ne va pas plus loin qu'un saut
