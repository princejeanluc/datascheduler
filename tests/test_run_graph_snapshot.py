"""
DataScheduler — tests/test_run_graph_snapshot.py
Lot atelier-suivi-execution : `pipeline_runs.graph_snapshot_json`, une photo figée des étapes et
liaisons au lancement de CHAQUE run (succès compris, contrairement à `resumable_state_json` qui ne
couvre que l'échec reprenable) — core/pipeline.py::_build_graph_snapshot_json. Sert à ce qu'une
vue de run reste fidèle à ce qui a réellement tourné même si le pipeline change ensuite.
"""

import json

import core.steps as steps_module
from core.pipeline import run_pipeline
from core.steps.base import BaseStep, StepResult
from database import db_manager as db


class _FakeStep(BaseStep):
    def run(self, ctx, cancel_event=None, on_progress=None) -> StepResult:
        return StepResult(success=True)


class _FakeFailingStep(BaseStep):
    def run(self, ctx, cancel_event=None, on_progress=None) -> StepResult:
        return StepResult(success=False, error="échec simulé")


def _edge(from_key, to_key, from_port="output_file", to_port="input"):
    return {"from_step_key": from_key, "from_port": from_port, "to_step_key": to_key, "to_port": to_port}


# ──────────────────────────────────────────────
#  Migration (une base antérieure à ce lot n'a pas la colonne)
# ──────────────────────────────────────────────

def test_a_pre_existing_pipeline_runs_table_gets_the_graph_snapshot_column_added(tmp_path):
    """Même patron que les autres tests de migration de pipeline_runs (voir test_db_manager.py) —
    exerce réellement le bloc ALTER TABLE ajouté à _migrate(), pas Base.metadata.create_all()."""
    from sqlalchemy import create_engine, text

    db_path = tmp_path / "legacy_runs_snapshot.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE pipeline_runs (id INTEGER PRIMARY KEY, pipeline_id INTEGER, "
            "started_at DATETIME, finished_at DATETIME, status VARCHAR(20), "
            "rows_exported INTEGER, remote_path VARCHAR(500), error_message TEXT, log_text TEXT)"
        ))
        conn.commit()
    engine.dispose()

    db.init_db(db_path)
    cols = {r[1] for r in create_engine(f"sqlite:///{db_path}").connect()
            .execute(text("PRAGMA table_info(pipeline_runs)")).fetchall()}
    assert "graph_snapshot_json" in cols

    db._engine = None
    db._SessionFactory = None


# ──────────────────────────────────────────────
#  Écriture par run_pipeline()
# ──────────────────────────────────────────────

def test_linear_run_persists_a_snapshot_with_the_full_step_config(test_db, monkeypatch):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeStep)

    pipeline = db.create_pipeline(name="snapshot-linear")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "label": "Extraire ventes",
         "config": {"_step_key": "extract", "query": "SELECT 1"},
         "retry_count": 2, "retry_interval_s": 30},
    ])

    result = run_pipeline(pipeline.id)
    assert result.success, result.error

    run = db.get_run(result.run_id)
    snapshot = json.loads(run.graph_snapshot_json)
    assert snapshot["edges"] == []
    assert len(snapshot["steps"]) == 1
    step = snapshot["steps"][0]
    assert step["step_key"] == "extract"
    assert step["step_type"] == "DB_EXTRACT"
    assert step["step_label"] == "Extraire ventes"
    assert step["config"]["query"] == "SELECT 1"
    assert step["retry_count"] == 2
    assert step["retry_interval_s"] == 30


def test_graph_run_persists_the_edges_in_the_snapshot(test_db, monkeypatch):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeStep)

    pipeline = db.create_pipeline(name="snapshot-graph")
    steps = [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
    ]
    edges = [_edge("a", "b")]
    db.save_pipeline_graph(pipeline.id, steps, edges)

    result = run_pipeline(pipeline.id)
    assert result.success, result.error

    run = db.get_run(result.run_id)
    snapshot = json.loads(run.graph_snapshot_json)
    assert snapshot["edges"] == [
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"}
    ]


def test_a_failed_run_also_persists_a_snapshot(test_db, monkeypatch):
    """Contrairement à resumable_state_json (échec reprenable seulement), la photo est prise pour
    TOUT run, succès ou échec."""
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeFailingStep)

    pipeline = db.create_pipeline(name="snapshot-failed")
    db.save_steps(pipeline.id, [{"step_type": "FTP_UPLOAD", "config": {"_step_key": "fails"}}])

    result = run_pipeline(pipeline.id)
    assert not result.success

    run = db.get_run(result.run_id)
    snapshot = json.loads(run.graph_snapshot_json)
    assert snapshot["steps"][0]["step_key"] == "fails"


def test_snapshot_is_unaffected_by_editing_the_pipeline_after_the_run(test_db, monkeypatch):
    """Le point central du lot : une exécution se joue sur une version figée du pipeline — un
    utilisateur qui modifie la structure après coup (ou pendant qu'un AUTRE run tourne) ne doit
    jamais faire dévier ce qu'une vue de run affiche pour CE run déjà enregistré."""
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeStep)

    pipeline = db.create_pipeline(name="snapshot-frozen")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "extract", "query": "SELECT 1"}},
    ])

    result = run_pipeline(pipeline.id)
    assert result.success, result.error

    # Modification du pipeline APRÈS le run : nouvelle requête, nouvelle étape ajoutée.
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "extract", "query": "SELECT 2"}},
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "extract_2", "query": "SELECT 3"}},
    ])

    run = db.get_run(result.run_id)
    snapshot = json.loads(run.graph_snapshot_json)
    assert len(snapshot["steps"]) == 1
    assert snapshot["steps"][0]["config"]["query"] == "SELECT 1"
