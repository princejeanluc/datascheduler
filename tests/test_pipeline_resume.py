"""
DataScheduler — tests/test_pipeline_resume.py
Vérifie la reprise depuis l'échec (chantier J.2) : persistance de l'état de reprise à l'échec,
étapes déjà réussies sautées à la reprise, invalidation propre (fichier disparu, config modifiée),
purge automatique d'un état périmé au run suivant, règle de sécurité run_always, restauration du
port actif d'un routeur CONDITION en mode graphe, et absence de corruption sous concurrence.

Même patron que tests/test_step_context_artifacts.py/test_pipeline_graph_engine.py : steps
factices substitués dans le registre, fixture test_db, round-trip complet via run_pipeline().
"""

import json
import threading
from pathlib import Path

import core.steps as steps_module
from core.pipeline import run_pipeline
from core.steps.base import BaseStep, StepResult
from database import db_manager as db

_calls: list[str] = []


class _FakeProducerStep(BaseStep):
    PRODUCES = {"output_file"}

    def run(self, ctx, cancel_event=None, on_progress=None) -> StepResult:
        _calls.append(self.config.get("label", "producer"))
        path = Path(self.config["path"])
        path.write_text(self.config.get("content", "x"))
        ctx.output_file = path
        return StepResult(success=True)


class _FakeFailingStep(BaseStep):
    REQUIRES = {"output_file"}

    def run(self, ctx, cancel_event=None, on_progress=None) -> StepResult:
        _calls.append(self.config.get("label", "failing"))
        return StepResult(success=False, error=self.config.get("error", "échec simulé"))


def _edge(from_key, to_key, from_port="output_file", to_port="input"):
    return {"from_step_key": from_key, "from_port": from_port, "to_step_key": to_key, "to_port": to_port}


def test_run_pipeline_persists_resumable_state_on_failure(test_db, monkeypatch, tmp_path):
    _calls.clear()
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeFailingStep)

    p1 = tmp_path / "p1.txt"
    pipeline = db.create_pipeline(name="test-resume-persist")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(p1), "content": "A", "_step_key": "prod", "label": "prod"}},
        {"step_type": "FTP_UPLOAD",  "config": {"_step_key": "fail", "label": "fail"}},
    ])

    result = run_pipeline(pipeline.id)

    assert not result.success
    resumable = db.get_last_resumable_run(pipeline.id)
    assert resumable is not None
    state = json.loads(resumable.resumable_state_json)
    assert state["completed_step_keys"] == ["prod"]
    assert p1.exists()   # pas nettoyé — préservé pour une reprise éventuelle


def test_resume_skips_completed_step_and_replays_failed_one(test_db, monkeypatch, tmp_path):
    _calls.clear()
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)

    class _SucceedsOnSecondCall(BaseStep):
        REQUIRES = {"output_file"}
        attempt = 0

        def run(self, ctx, cancel_event=None, on_progress=None):
            _calls.append("fail")
            _SucceedsOnSecondCall.attempt += 1
            if _SucceedsOnSecondCall.attempt < 2:
                return StepResult(success=False, error="échec simulé (1re tentative)")
            return StepResult(success=True)

    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _SucceedsOnSecondCall)

    p1 = tmp_path / "p1.txt"
    pipeline = db.create_pipeline(name="test-resume-replay")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(p1), "content": "A", "_step_key": "prod", "label": "prod"}},
        {"step_type": "FTP_UPLOAD",  "config": {"_step_key": "fail"}},
    ])

    first = run_pipeline(pipeline.id)
    assert not first.success
    assert _calls.count("prod") == 1

    resumable = db.get_last_resumable_run(pipeline.id)
    second = run_pipeline(pipeline.id, resume_from_run_id=resumable.id)

    assert second.success, second.error
    assert _calls.count("prod") == 1   # jamais rejouée
    assert _calls.count("fail") == 2   # 1re tentative (échec) + reprise (succès)


def test_successful_resume_clears_resumable_state(test_db, monkeypatch, tmp_path):
    _calls.clear()
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)

    class _SucceedsOnSecondCall(BaseStep):
        REQUIRES = {"output_file"}
        attempt = 0

        def run(self, ctx, cancel_event=None, on_progress=None):
            _SucceedsOnSecondCall.attempt += 1
            if _SucceedsOnSecondCall.attempt < 2:
                return StepResult(success=False, error="échec simulé")
            return StepResult(success=True)

    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _SucceedsOnSecondCall)

    p1 = tmp_path / "p1.txt"
    pipeline = db.create_pipeline(name="test-resume-clears")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(p1), "content": "A", "_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD",  "config": {"_step_key": "fail"}},
    ])

    first = run_pipeline(pipeline.id)
    resumable = db.get_last_resumable_run(pipeline.id)
    run_pipeline(pipeline.id, resume_from_run_id=resumable.id)

    assert db.get_last_resumable_run(pipeline.id) is None


def test_resume_fails_cleanly_when_artifact_file_missing(test_db, monkeypatch, tmp_path):
    _calls.clear()
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeFailingStep)

    p1 = tmp_path / "p1.txt"
    pipeline = db.create_pipeline(name="test-resume-missing-file")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(p1), "content": "A", "_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD",  "config": {"_step_key": "fail"}},
    ])

    run_pipeline(pipeline.id)
    resumable = db.get_last_resumable_run(pipeline.id)
    p1.unlink()   # simule un fichier temporaire expiré/supprimé manuellement

    result = run_pipeline(pipeline.id, resume_from_run_id=resumable.id)

    assert not result.success
    assert "Reprise impossible" in result.error


def test_resume_fails_cleanly_when_step_config_changed(test_db, monkeypatch, tmp_path):
    _calls.clear()
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeFailingStep)

    p1 = tmp_path / "p1.txt"
    pipeline = db.create_pipeline(name="test-resume-config-changed")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(p1), "content": "A", "_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD",  "config": {"_step_key": "fail"}},
    ])

    run_pipeline(pipeline.id)
    resumable = db.get_last_resumable_run(pipeline.id)

    # Simule une édition du pipeline entre l'échec et la reprise — même _step_key (préservé par
    # save_steps()), mais un contenu de config différent pour l'étape déjà "réussie".
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(p1), "content": "B — modifié", "_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD",  "config": {"_step_key": "fail"}},
    ])

    result = run_pipeline(pipeline.id, resume_from_run_id=resumable.id)

    assert not result.success
    assert "Reprise impossible" in result.error


def test_new_normal_run_purges_stale_resumable_state_and_its_files(test_db, monkeypatch, tmp_path):
    _calls.clear()
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeFailingStep)

    p1 = tmp_path / "p1.txt"
    p2 = tmp_path / "p2.txt"   # chemin distinct pour le 2e run — prouve que p1 est bien purgé,
                                # pas seulement réécrit incidemment au même chemin
    pipeline = db.create_pipeline(name="test-resume-purge")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(p1), "content": "A", "_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD",  "config": {"_step_key": "fail"}},
    ])

    run_pipeline(pipeline.id)
    assert db.get_last_resumable_run(pipeline.id) is not None
    assert p1.exists()

    # Nouveau run normal (pas une reprise) — doit balayer l'état précédent et son fichier, avant
    # même de commencer sa propre exécution.
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(p2), "content": "A2", "_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD",  "config": {"_step_key": "fail"}},
    ])
    run_pipeline(pipeline.id)

    assert db.get_last_resumable_run(pipeline.id) is not None   # le NOUVEL échec en a un à lui
    assert not p1.exists()   # l'ancien fichier a bien été purgé, pas seulement remplacé
    assert p2.exists()       # le nouveau run a bien produit le sien


def test_run_always_step_succeeding_after_failure_never_becomes_resumable(test_db, monkeypatch, tmp_path):
    _calls.clear()
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeFailingStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeProducerStep)

    p1 = tmp_path / "p1.txt"
    p3 = tmp_path / "p3.txt"
    pipeline = db.create_pipeline(name="test-resume-run-always")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(p1), "content": "A", "_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD",  "config": {"_step_key": "fail"}},
        {"step_type": "LOCAL_COPY",  "config": {"path": str(p3), "content": "C", "_step_key": "notif"},
         "run_always": True},
    ])

    result = run_pipeline(pipeline.id)

    assert not result.success
    resumable = db.get_last_resumable_run(pipeline.id)
    assert resumable is not None
    state = json.loads(resumable.resumable_state_json)
    assert state["completed_step_keys"] == ["prod"]   # "notif" a réussi mais reste exclu


def test_resume_restores_active_port_for_a_condition_router_in_graph_mode(test_db, monkeypatch, tmp_path):
    _calls.clear()
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "DB_LOAD", _FakeProducerStep)      # branche "false"
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeProducerStep)  # branche "true" (jamais sélectionnée)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeFailingStep)   # après la branche "false"

    p_prod  = tmp_path / "prod.txt"
    p_false = tmp_path / "false_branch.txt"
    p_true  = tmp_path / "true_branch.txt"

    pipeline = db.create_pipeline(name="test-resume-condition-port")
    db.save_pipeline_graph(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(p_prod), "content": "A", "_step_key": "prod", "label": "prod"}},
        {"step_type": "CONDITION",  "config": {"expression": "rows_count > 0", "_step_key": "cond"}},
        {"step_type": "DB_LOAD",    "config": {"path": str(p_false), "content": "F", "_step_key": "on_false", "label": "on_false"}},
        {"step_type": "FTP_UPLOAD", "config": {"path": str(p_true), "content": "T", "_step_key": "on_true", "label": "on_true"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "after", "label": "after"}},
    ], edges=[
        _edge("prod", "cond"),
        _edge("cond", "on_true", from_port="true"),
        _edge("cond", "on_false", from_port="false"),
        _edge("on_false", "after"),
    ])

    first = run_pipeline(pipeline.id)
    assert not first.success
    assert not p_true.exists()   # branche "true" jamais sélectionnée (rows_count == 0)

    resumable = db.get_last_resumable_run(pipeline.id)
    second = run_pipeline(pipeline.id, resume_from_run_id=resumable.id)

    assert not second.success   # "after" (LOCAL_COPY, factice en échec) échoue à nouveau — non testé ici
    assert not p_true.exists()   # toujours jamais exécutée — preuve que le port actif "false" de
                                  # "cond" a bien été restauré, sinon on_true aurait été réévaluée
                                  # comme disponible et se serait exécutée à tort.
    assert _calls.count("prod") == 1
    assert _calls.count("on_false") == 1
    assert _calls.count("after") == 2   # rejouée à la reprise


def test_concurrent_run_pipeline_calls_do_not_corrupt_resumable_state(test_db, monkeypatch, tmp_path):
    _calls.clear()
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeFailingStep)

    p1 = tmp_path / "p1.txt"
    pipeline = db.create_pipeline(name="test-resume-concurrency")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(p1), "content": "A", "_step_key": "prod"}},
        {"step_type": "FTP_UPLOAD",  "config": {"_step_key": "fail"}},
    ])

    run_pipeline(pipeline.id)   # produit un premier état de reprise

    results = []

    def _run():
        results.append(run_pipeline(pipeline.id))

    threads = [threading.Thread(target=_run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # run_pipeline() ne lève jamais — une vraie collision de fichiers (deux threads unlink()ant
    # le même chemin en parallèle) remonterait donc comme un échec "Exception inattendue : ..."
    # (le seul chemin de ce module qui capture une exception brute plutôt qu'un message métier
    # clair) plutôt que comme un résultat métier normal (échec de "fail", ou reprise refusée
    # proprement) — c'est précisément ce que le verrou de la section réclamation empêche.
    assert len(results) == 2
    for r in results:
        assert "Exception inattendue" not in (r.error or "")
