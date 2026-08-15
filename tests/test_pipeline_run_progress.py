"""
DataScheduler — tests/test_pipeline_run_progress.py
Vérifie l'écriture incrémentale de la progression pendant l'exécution (chantier N) :
PipelineRun.current_step_label/log_text sont mis à jour AU FUR ET À MESURE, pas seulement une
fois à la fin — jusqu'ici run_pipeline() n'écrivait qu'un seul commit final (db.finish_run()),
donc consulter le run pendant qu'il tourne encore (dialogue de log, liste des pipelines) ne
montrait jamais rien. Même patron que tests/test_pipeline_resume.py : steps factices substitués
dans le registre, fixture test_db, round-trip via run_pipeline().
"""

import core.steps as steps_module
from core.pipeline import run_pipeline
from core.steps.base import BaseStep, StepResult
from database import db_manager as db

_captured: dict = {}


class _FakeStepA(BaseStep):
    def run(self, ctx, on_progress=None):
        return StepResult(success=True)


class _FakeStepBReadsBackMidRun(BaseStep):
    """Au moment où CETTE étape s'exécute, l'étape précédente (A) a déjà terminé — le run doit
    déjà porter la trace de sa progression en base, avant même que le pipeline ne se termine."""

    def run(self, ctx, on_progress=None):
        run = db.get_runs(_captured["pipeline_id"])[0]
        _captured["mid_run_current_step_label"] = run.current_step_label
        _captured["mid_run_log_text"] = run.log_text
        _captured["mid_run_status"] = str(run.status)
        return StepResult(success=True)


def test_run_pipeline_persists_progress_incrementally_not_only_at_the_end(test_db, monkeypatch):
    _captured.clear()
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeStepA)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeStepBReadsBackMidRun)

    pipeline = db.create_pipeline(name="test-run-progress")
    _captured["pipeline_id"] = pipeline.id
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "label": "Étape A", "config": {}},
        {"step_type": "FTP_UPLOAD", "label": "Étape B", "config": {}},
    ])

    result = run_pipeline(pipeline.id)

    assert result.success
    # Preuve que l'écriture est incrémentale : au moment où B s'exécute (avant la fin du run),
    # current_step_label reflète déjà la transition vers B (écrite par progress() juste avant
    # que son exécuteur ne démarre), et log_text contient déjà la trace complète de A — ni l'un
    # ni l'autre n'auraient de contenu utile à ce stade si l'écriture n'avait lieu qu'au tout
    # dernier commit (db.finish_run()), qui n'a pas encore eu lieu (statut encore RUNNING).
    assert "Étape B" in _captured["mid_run_current_step_label"]
    assert "Étape A" in _captured["mid_run_log_text"]
    assert _captured["mid_run_status"] == "PipelineStatus.RUNNING"

    # État final cohérent : current_step_label nettoyé par finish_run(), log complet préservé.
    final_run = db.get_run(result.run_id)
    assert final_run.current_step_label is None
    assert "Étape A" in final_run.log_text
    assert "Étape B" in final_run.log_text


def test_run_pipeline_progress_never_written_before_the_run_row_exists(test_db, monkeypatch):
    """Avant db.create_run() (ex : pipeline introuvable), progress() est appelée (ligne
    "Chargement…") mais ne doit tenter aucune écriture DB — run_id vaut encore None à ce
    moment."""
    result = run_pipeline(999_999)   # pipeline inexistant — échoue avant create_run()
    assert not result.success
    assert result.run_id is None


class _FakeStepAReadsBackMidRunKey(BaseStep):
    """Traçage lumineux (chantier identité, vague 4) : au moment où CETTE étape s'exécute,
    current_step_key doit déjà refléter SA _step_key — c'est ce que l'éditeur graphique
    interroge en continu pour savoir quel nœud surligner."""

    def run(self, ctx, on_progress=None):
        run = db.get_runs(_captured["pipeline_id"])[0]
        _captured["mid_run_current_step_key"] = run.current_step_key
        return StepResult(success=True)


def test_run_pipeline_persists_current_step_key_incrementally(test_db, monkeypatch):
    _captured.clear()
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeStepAReadsBackMidRunKey)

    pipeline = db.create_pipeline(name="test-run-progress-key")
    _captured["pipeline_id"] = pipeline.id
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "label": "Étape A", "config": {"_step_key": "key-a"}},
    ])

    result = run_pipeline(pipeline.id)

    assert result.success
    assert _captured["mid_run_current_step_key"] == "key-a"
    # Nettoyé à la fin, comme current_step_label.
    final_run = db.get_run(result.run_id)
    assert final_run.current_step_key is None
