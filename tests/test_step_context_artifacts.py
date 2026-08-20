"""
DataScheduler — tests/test_step_context_artifacts.py
Vérifie le ciblage explicite de source (StepContext.artifacts nommés/adressables) :
validate_step_sequence en isolation, puis l'exécuteur de bout en bout avec des steps
factices substitués dans le registre.
"""

from pathlib import Path

import pytest

from core.pipeline import validate_step_sequence, run_pipeline
from core.steps.base import BaseStep, StepResult
import core.steps as steps_module
from database import db_manager as db


# ──────────────────────────────────────────────
#  validate_step_sequence — dicts en mémoire, pas de DB
# ──────────────────────────────────────────────

def test_default_behavior_unchanged_without_targeting():
    steps = [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "DB_LOAD",    "config": {}},
    ]
    errors, warnings = validate_step_sequence(steps)
    assert errors == []
    assert warnings == []


def test_default_behavior_still_flags_missing_producer():
    steps = [{"step_type": "DB_LOAD", "config": {}}]
    errors, warnings = validate_step_sequence(steps)
    assert len(errors) == 1
    assert "nécessite" in errors[0]


def test_explicit_targeting_of_valid_prior_step_is_accepted():
    steps = [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "prod1"}},
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "prod2"}},
        {"step_type": "DB_LOAD",    "config": {"reads_from_step_key": "prod1"}},
    ]
    errors, warnings = validate_step_sequence(steps)
    assert errors == []


def test_explicit_targeting_of_a_step_not_yet_produced_is_blocking():
    steps = [
        {"step_type": "DB_LOAD", "config": {"reads_from_step_key": "does_not_exist_yet"}},
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "prod1"}},
    ]
    errors, warnings = validate_step_sequence(steps)
    assert len(errors) == 1
    assert "source ciblée" in errors[0]


def test_explicit_targeting_becomes_warning_when_run_always():
    steps = [
        {"step_type": "DB_LOAD", "config": {"reads_from_step_key": "missing"}, "run_always": True},
    ]
    errors, warnings = validate_step_sequence(steps)
    assert errors == []
    assert len(warnings) == 1


# ──────────────────────────────────────────────
#  Exécuteur de bout en bout — steps factices substitués dans le registre
# ──────────────────────────────────────────────

class _FakeProducerStep(BaseStep):
    PRODUCES = {"output_file"}

    def run(self, ctx, cancel_event=None, on_progress=None) -> StepResult:
        result = StepResult()
        path = Path(self.config["path"])
        path.write_text(self.config["content"])
        ctx.output_file = path
        result.success = True
        return result


class _FakeConsumerStep(BaseStep):
    REQUIRES = {"output_file"}

    def run(self, ctx, cancel_event=None, on_progress=None) -> StepResult:
        result = StepResult()
        sink = Path(self.config["sink_path"])
        sink.write_text(ctx.output_file.read_text() if ctx.output_file else "")
        result.success = True
        return result


def test_run_pipeline_respects_explicit_source_targeting(test_db, monkeypatch, tmp_path):
    # Réutilise des StepType existants (contrainte d'enum en base) — seule la classe qui
    # les exécute est substituée pour la durée du test.
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)

    p1 = tmp_path / "producer1.txt"
    p2 = tmp_path / "producer2.txt"
    sink = tmp_path / "sink.txt"

    pipeline = db.create_pipeline(name="test-targeting")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(p1), "content": "FROM_PRODUCER_1", "_step_key": "prod1"}},
        {"step_type": "DB_EXTRACT", "config": {"path": str(p2), "content": "FROM_PRODUCER_2", "_step_key": "prod2"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(sink), "reads_from_step_key": "prod1"}},
    ])

    result = run_pipeline(pipeline.id)

    assert result.success, result.error
    assert sink.read_text() == "FROM_PRODUCER_1"


def test_run_pipeline_defaults_to_most_recent_producer_without_targeting(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducerStep)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeConsumerStep)

    p1 = tmp_path / "producer1.txt"
    p2 = tmp_path / "producer2.txt"
    sink = tmp_path / "sink.txt"

    pipeline = db.create_pipeline(name="test-default-behavior")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {"path": str(p1), "content": "FROM_PRODUCER_1", "_step_key": "prod1"}},
        {"step_type": "DB_EXTRACT", "config": {"path": str(p2), "content": "FROM_PRODUCER_2", "_step_key": "prod2"}},
        {"step_type": "LOCAL_COPY", "config": {"sink_path": str(sink)}},  # pas de ciblage explicite
    ])

    result = run_pipeline(pipeline.id)

    assert result.success, result.error
    assert sink.read_text() == "FROM_PRODUCER_2"  # comportement historique : le plus récent
