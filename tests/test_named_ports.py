"""
DataScheduler — tests/test_named_ports.py
Vérifie les ports de sortie nommés (chantier UX post-personas, persona "Julien") : le token
générique {artifact:nom} dans resolve_tokens(), la publication d'un alias en plus de _step_key à
l'exécution, et la détection de collision de noms — tout en couche cosmétique par-dessus le
mécanisme stable existant (_step_key), jamais un remplacement (voir core/pipeline.py).
"""

from pathlib import Path

import core.steps as steps_module
from core.pipeline import (
    validate_step_sequence, validate_pipeline_graph, run_pipeline,
    _duplicate_output_name_errors,
)
from core.steps.base import BaseStep, StepContext, StepResult
from database import db_manager as db


# ──────────────────────────────────────────────
#  resolve_tokens() — token générique {artifact:nom}
# ──────────────────────────────────────────────

def test_artifact_token_resolves_when_present():
    ctx = StepContext()
    ctx.artifacts["ventes_csv"] = "/tmp/ventes.csv"
    assert ctx.resolve_tokens("--input {artifact:ventes_csv}") == "--input /tmp/ventes.csv"


def test_artifact_token_stays_literal_when_absent():
    ctx = StepContext()
    assert ctx.resolve_tokens("--input {artifact:inconnu}") == "--input {artifact:inconnu}"


def test_artifact_token_coexists_with_existing_tokens():
    ctx = StepContext()
    ctx.rows_count = 42
    ctx.artifacts["ventes_csv"] = "/tmp/ventes.csv"
    result = ctx.resolve_tokens("{rows_count} lignes, fichier {artifact:ventes_csv}")
    assert result == "42 lignes, fichier /tmp/ventes.csv"


# ──────────────────────────────────────────────
#  Validation — unicité des noms de sortie
# ──────────────────────────────────────────────

def test_no_error_when_no_custom_output_names():
    """Deux DB_EXTRACT sans nom personnalisé (le cas courant aujourd'hui) ne doivent jamais
    être signalés en collision — seul un nom explicitement choisi compte."""
    steps = [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "b"}},
    ]
    assert _duplicate_output_name_errors(steps) == []
    errors, _ = validate_step_sequence(steps)
    assert errors == []


def test_duplicate_output_name_is_blocking_error():
    steps = [
        {"step_type": "DB_EXTRACT", "label": "Extract A", "config": {"_step_key": "a", "output_name": "ventes"}},
        {"step_type": "DB_EXTRACT", "label": "Extract B", "config": {"_step_key": "b", "output_name": "ventes"}},
    ]
    errors, _ = validate_step_sequence(steps)
    assert len(errors) == 1
    assert "ventes" in errors[0]
    assert "Extract A" in errors[0] and "Extract B" in errors[0]


def test_distinct_output_names_are_accepted():
    steps = [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a", "output_name": "ventes"}},
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "b", "output_name": "achats"}},
    ]
    errors, _ = validate_step_sequence(steps)
    assert errors == []


def test_validate_pipeline_graph_also_checks_output_name_collisions():
    steps = [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a", "output_name": "ventes"}},
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "b", "output_name": "ventes"}},
    ]
    errors, _ = validate_pipeline_graph(steps, edges=[])
    assert any("ventes" in e for e in errors)


def test_output_names_plural_participates_in_collision_check():
    """PYTHON_SCRIPT auto-déclare plusieurs noms via output_names — comptent aussi."""
    steps = [
        {"step_type": "PYTHON_SCRIPT", "label": "Script A", "config": {"_step_key": "a", "output_names": ["rapport"]}},
        {"step_type": "DB_EXTRACT", "label": "Extract B", "config": {"_step_key": "b", "output_name": "rapport"}},
    ]
    errors, _ = validate_step_sequence(steps)
    assert len(errors) == 1


# ──────────────────────────────────────────────
#  Exécution — l'alias ne remplace jamais _step_key
# ──────────────────────────────────────────────

class _FakeProducer(BaseStep):
    PRODUCES = {"output_file"}

    def run(self, ctx, on_progress=None):
        path = Path(self.config["path"])
        path.write_text(self.config.get("content", "DATA"))
        ctx.output_file = path
        return StepResult(success=True)


class _FakeSink(BaseStep):
    REQUIRES = {"output_file"}

    def run(self, ctx, on_progress=None):
        Path(self.config["sink_path"]).write_text(ctx.output_file.read_text() if ctx.output_file else "")
        return StepResult(success=True)


def test_output_name_alias_published_alongside_step_key(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducer)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeSink)

    src  = tmp_path / "src.txt"
    sink = tmp_path / "sink.txt"

    pipeline = db.create_pipeline(name="named-port-test")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT",
         "config": {"path": str(src), "content": "HELLO", "_step_key": "prod", "output_name": "ventes_csv"}},
        {"step_type": "LOCAL_COPY",
         "config": {"sink_path": str(sink), "reads_from_step_key": "prod"}},
    ])

    result = run_pipeline(pipeline.id)

    assert result.success, result.error
    assert sink.read_text() == "HELLO"   # le câblage historique (_step_key) fonctionne toujours


def test_renaming_output_name_does_not_break_step_key_wiring(test_db, monkeypatch, tmp_path):
    """Le point central de la décision de conception : renommer output_name ne casse jamais
    le graphe, seul le câblage par _step_key/reads_from_step_key compte pour l'exécution."""
    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducer)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeSink)

    src  = tmp_path / "src.txt"
    sink = tmp_path / "sink.txt"

    pipeline = db.create_pipeline(name="rename-test")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT",
         "config": {"path": str(src), "content": "HELLO", "_step_key": "prod", "output_name": "ancien_nom"}},
        {"step_type": "LOCAL_COPY",
         "config": {"sink_path": str(sink), "reads_from_step_key": "prod"}},
    ])
    # "Renommage" : un ré-enregistrement avec un output_name différent, _step_key inchangé.
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT",
         "config": {"path": str(src), "content": "HELLO", "_step_key": "prod", "output_name": "nouveau_nom"}},
        {"step_type": "LOCAL_COPY",
         "config": {"sink_path": str(sink), "reads_from_step_key": "prod"}},
    ])

    result = run_pipeline(pipeline.id)
    assert result.success, result.error
    assert sink.read_text() == "HELLO"
