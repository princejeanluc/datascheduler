"""
DataScheduler — tests/test_run_log_json.py
Lot D2-D4 (DONNEES.md::D3) : pipeline_runs.log_json, journal à niveaux en parallèle de log_text
(jamais retiré). PipelineResult.log()/fail() construisent self.log_entries en plus de
self.log_lines ; log_json est persisté via finish_run() et, en continu, update_run_progress().
"""

import json

import core.steps as steps_module
from core.pipeline import PipelineResult, run_pipeline
from core.steps.base import BaseStep, StepResult
from database import db_manager as db


class _FakeStep(BaseStep):
    def run(self, ctx, cancel_event=None, on_progress=None) -> StepResult:
        return StepResult(success=True)


class _FakeFailingStep(BaseStep):
    def run(self, ctx, cancel_event=None, on_progress=None) -> StepResult:
        return StepResult(success=False, error="échec simulé")


def test_log_appends_an_info_entry_alongside_the_plain_text_line():
    result = PipelineResult()
    result.log("Chargement…")

    assert "Chargement…" in result.log_lines[0]   # log_text inchangé, toujours construit
    assert len(result.log_entries) == 1
    entry = result.log_entries[0]
    assert entry["lvl"] == "INFO"
    assert entry["msg"] == "Chargement…"
    assert entry["step_key"] is None
    assert "t" in entry


def test_fail_appends_an_error_level_entry():
    result = PipelineResult()
    result.fail("Connexion refusée")

    assert result.log_entries[-1]["lvl"] == "ERROR"
    assert result.log_entries[-1]["msg"] == "ERREUR : Connexion refusée"


def test_log_json_property_serializes_all_entries():
    result = PipelineResult()
    result.log("Première ligne")
    result.fail("Deuxième ligne")

    entries = json.loads(result.log_json)
    assert [e["lvl"] for e in entries] == ["INFO", "ERROR"]


def test_a_successful_run_persists_log_json(test_db, monkeypatch):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeStep)
    p = db.create_pipeline(name="log-json-success")
    db.save_steps(p.id, [{"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}}])

    result = run_pipeline(p.id)
    assert result.success, result.error

    run = db.get_run(result.run_id)
    entries = json.loads(run.log_json)
    assert len(entries) > 0
    assert all(e["lvl"] in ("INFO", "WARN", "ERROR", "OK") for e in entries)
    # log_text continue d'être écrit à l'identique — jamais retiré (D1/B1, même garantie).
    assert run.log_text


def test_a_failed_run_persists_an_error_level_entry(test_db, monkeypatch):
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeFailingStep)
    p = db.create_pipeline(name="log-json-failed")
    db.save_steps(p.id, [{"step_type": "FTP_UPLOAD", "config": {"_step_key": "a"}}])

    result = run_pipeline(p.id)
    assert not result.success

    run = db.get_run(result.run_id)
    entries = json.loads(run.log_json)
    assert any(e["lvl"] == "ERROR" for e in entries)
