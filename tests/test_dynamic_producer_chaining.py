"""
DataScheduler — tests/test_dynamic_producer_chaining.py
Bug réel signalé par l'utilisateur : un pipeline graphe SPARK_SQL (résultat récupéré) → LOCAL_COPY
échouait avec "Aucun fichier source disponible", alors que Spark avait bien produit le fichier.

Cause : SPARK_SQL déclare volontairement un PRODUCES statique vide (la production dépend de la
case "Récupérer le résultat", pas connaissable par la seule classe) — mais 3 endroits du code
utilisaient ce PRODUCES statique comme si "vide" voulait dire "ne produit jamais" :
1. _execute_graph/_execute_linear (core/pipeline.py) ne publiaient ctx.artifacts[step_key] que si
   "output_file" figurait dans le PRODUCES statique — jamais vrai pour SPARK_SQL — donc l'étape en
   aval, en se réorientant sur ctx.artifacts.get(step_key), récupérait None et écrasait la bonne
   valeur que SPARK_SQL avait pourtant bien posée sur ctx.output_file.
2. validate_step_sequence (éditeur linéaire) avait la même lacune pour available_keys.
3. Le sélecteur "Source" de l'éditeur (_source_row) filtrait les étapes candidates avec le même
   PRODUCES statique — SPARK_SQL n'apparaissait donc jamais dans la liste, quelle que soit sa
   config (c'est le "un seul choix disponible" also signalé par l'utilisateur).

Fixé en basant la publication runtime sur un vrai changement de ctx.output_file observé après
l'exécution (plutôt que sur le PRODUCES statique), et en ajoutant step_produces_output_file()
(core/steps/__init__.py) qui sait que SPARK_SQL produit conditionnellement à sa config
("fetch_result") — utilisé à la fois par la validation et par le sélecteur "Source".

Un _FakeDynamicProducerStep (PRODUCES vide, comme SPARK_SQL) reproduit le bug indépendamment de
tout mock paramiko/SSH — même esprit que _FakeProducerStep dans test_pipeline_graph_engine.py.
"""

from pathlib import Path

import core.steps as steps_module
from core.pipeline import validate_step_sequence, run_pipeline
from core.steps import step_produces_output_file
from core.steps.base import BaseStep, StepResult
from database import db_manager as db


class _FakeDynamicProducerStep(BaseStep):
    """Mime SPARK_SQL : PRODUCES statique vide, mais produit réellement un fichier à l'exécution
    quand self.config['produce'] est vrai — exactement le même genre de production conditionnelle
    à la config que fetch_result."""

    def run(self, ctx, on_progress=None) -> StepResult:
        if self.config.get("produce", True):
            path = Path(self.config["path"])
            path.write_text(self.config.get("content", ""))
            ctx.output_file = path
        return StepResult(success=True)


def _edge(from_key, to_key, from_port="output_file", to_port="input"):
    return {"from_step_key": from_key, "from_port": from_port, "to_step_key": to_key, "to_port": to_port}


# ──────────────────────────────────────────────
#  step_produces_output_file — cas SPARK_SQL
# ──────────────────────────────────────────────

def test_step_produces_output_file_true_when_fetch_result_checked():
    assert step_produces_output_file("SPARK_SQL", {"fetch_result": True}) is True


def test_step_produces_output_file_false_when_fetch_result_unchecked():
    assert step_produces_output_file("SPARK_SQL", {"fetch_result": False}) is False
    assert step_produces_output_file("SPARK_SQL", {}) is False


def test_step_produces_output_file_true_for_static_producer():
    assert step_produces_output_file("DB_EXTRACT", {}) is True


def test_step_produces_output_file_false_for_non_producer():
    assert step_produces_output_file("EMAIL_NOTIFY", {}) is False


# ──────────────────────────────────────────────
#  Exécution graphe — reproduction exacte du bug signalé
# ──────────────────────────────────────────────

def test_graph_chains_a_dynamic_producer_into_a_consumer(test_db, monkeypatch, tmp_path):
    """Régression : SPARK_SQL (fetch_result=True) → LOCAL_COPY via une arête, dans l'éditeur
    graphe — échouait avec "Aucun fichier source disponible" avant le correctif. LOCAL_COPY
    n'est volontairement PAS mocké ici : c'est le vrai step (et son vrai message d'erreur) qui a
    été touché par le bug signalé."""
    monkeypatch.setitem(steps_module._REGISTRY, "SPARK_SQL", _FakeDynamicProducerStep)

    src      = tmp_path / "src.csv"
    dest_dir = tmp_path / "dest"

    pipeline = db.create_pipeline(name="graph-dynamic-producer")
    steps = [
        {"step_type": "SPARK_SQL", "config": {"path": str(src), "content": "a,b\n1,2\n", "produce": True, "_step_key": "spark"}},
        {"step_type": "LOCAL_COPY", "config": {"dest_dir": str(dest_dir), "_step_key": "copy"}},
    ]
    edges = [_edge("spark", "copy")]
    db.save_pipeline_graph(pipeline.id, steps, edges)

    result = run_pipeline(pipeline.id)

    assert result.success, result.error
    assert (dest_dir / "src.csv").read_text() == "a,b\n1,2\n"


def test_graph_dynamic_producer_not_producing_still_reports_missing_source(test_db, monkeypatch, tmp_path):
    """Le correctif ne doit pas masquer un vrai cas d'échec : si l'étape amont ne produit
    effectivement rien (produce=False, l'équivalent de fetch_result décoché), LOCAL_COPY doit
    toujours échouer avec son message habituel — pas de faux positif introduit par le correctif."""
    monkeypatch.setitem(steps_module._REGISTRY, "SPARK_SQL", _FakeDynamicProducerStep)

    pipeline = db.create_pipeline(name="graph-dynamic-producer-no-fetch")
    steps = [
        {"step_type": "SPARK_SQL", "config": {"produce": False, "_step_key": "spark"}},
        {"step_type": "LOCAL_COPY", "config": {"dest_dir": str(tmp_path / "dest"), "_step_key": "copy"}},
    ]
    edges = [_edge("spark", "copy")]
    db.save_pipeline_graph(pipeline.id, steps, edges)

    result = run_pipeline(pipeline.id)

    assert not result.success
    assert "Aucun fichier source disponible" in (result.error or "")


# ──────────────────────────────────────────────
#  Exécution linéaire — même bug via reads_from_step_key
# ──────────────────────────────────────────────

def test_linear_explicit_source_targets_a_dynamic_producer(test_db, monkeypatch, tmp_path):
    monkeypatch.setitem(steps_module._REGISTRY, "SPARK_SQL", _FakeDynamicProducerStep)

    src      = tmp_path / "src.csv"
    dest_dir = tmp_path / "dest"

    pipeline = db.create_pipeline(name="linear-dynamic-producer")
    db.save_steps(pipeline.id, [
        {"step_type": "SPARK_SQL", "config": {"path": str(src), "content": "x,y\n9,9\n", "produce": True, "_step_key": "spark"}},
        {"step_type": "LOCAL_COPY", "config": {"dest_dir": str(dest_dir), "reads_from_step_key": "spark"}},
    ])

    result = run_pipeline(pipeline.id)

    assert result.success, result.error
    assert (dest_dir / "src.csv").read_text() == "x,y\n9,9\n"


# ──────────────────────────────────────────────
#  validate_step_sequence — ne bloque plus un ciblage explicite d'un producteur dynamique
# ──────────────────────────────────────────────

def test_validate_step_sequence_accepts_explicit_target_on_dynamic_producer():
    steps = [
        {"step_type": "SPARK_SQL", "config": {"_step_key": "spark", "fetch_result": True}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "copy", "reads_from_step_key": "spark"}},
    ]
    errors, warnings = validate_step_sequence(steps)
    assert errors == []


def test_validate_step_sequence_still_blocks_when_producer_config_says_no_fetch():
    steps = [
        {"step_type": "SPARK_SQL", "config": {"_step_key": "spark", "fetch_result": False}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "copy", "reads_from_step_key": "spark"}},
    ]
    errors, warnings = validate_step_sequence(steps)
    assert len(errors) == 1
    assert "spark" not in errors[0]  # message générique, pas de fuite de la clé interne
