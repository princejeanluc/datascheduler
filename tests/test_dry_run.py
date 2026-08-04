"""
DataScheduler — tests/test_dry_run.py
Vérifie core.pipeline.dry_run_pipeline() (chantier UX autonomie, C.2) : forme du pipeline, prise
en compte des références manquantes (erreur bloquante) et des échecs de connexion réelle
(avertissement, pas bloquant), bascule linéaire/graphe identique à run_pipeline().
"""

import json

from database import db_manager as db
from core.pipeline import dry_run_pipeline


def _profile_and_query():
    profile = db.create_oracle_profile(
        name="ORA1", host="127.0.0.1", port=1521, username="u", password="p", service_name="SVC",
    )
    query = db.create_sql_query(name="Q1", sql_text="SELECT 1 FROM DUAL")
    return profile, query


def test_valid_pipeline_succeeds_without_connection_test(test_db):
    profile, query = _profile_and_query()
    p = db.create_pipeline(name="dryrun-valid")
    db.save_steps(p.id, [{
        "step_type": "DB_EXTRACT",
        "config": {"db_type": "ORACLE", "profile_id": profile.id, "sql_query_id": query.id},
    }])

    result = dry_run_pipeline(p.id, test_connections=False)
    assert result.success
    assert result.errors == []
    assert result.checked_connections == 0


def test_connection_failure_is_a_warning_not_an_error(test_db):
    profile, query = _profile_and_query()
    p = db.create_pipeline(name="dryrun-conn-fail")
    db.save_steps(p.id, [{
        "step_type": "DB_EXTRACT",
        "config": {"db_type": "ORACLE", "profile_id": profile.id, "sql_query_id": query.id},
    }])

    result = dry_run_pipeline(p.id, test_connections=True)
    assert result.success            # avertissement seulement, pas bloquant
    assert result.checked_connections == 1
    assert len(result.warnings) == 1
    assert "db_profile" in result.warnings[0]


def test_missing_reference_is_a_hard_error(test_db):
    profile, query = _profile_and_query()
    p = db.create_pipeline(name="dryrun-missing-ref")
    db.save_steps(p.id, [{
        "step_type": "DB_EXTRACT",
        "config": {"db_type": "ORACLE", "profile_id": 999999, "sql_query_id": query.id},
    }])

    result = dry_run_pipeline(p.id, test_connections=False)
    assert not result.success
    assert len(result.errors) == 1
    assert "n'existe plus" in result.errors[0]


def test_sql_query_reference_not_counted_as_connection(test_db):
    profile, query = _profile_and_query()
    p = db.create_pipeline(name="dryrun-sql-query-not-counted")
    db.save_steps(p.id, [{
        "step_type": "DB_EXTRACT",
        "config": {"db_type": "ORACLE", "profile_id": profile.id, "sql_query_id": query.id},
    }])

    result = dry_run_pipeline(p.id, test_connections=True)
    # Un seul appel de connexion réel (le profil db), pas deux (sql_query n'est pas testé).
    assert result.checked_connections == 1


def test_empty_pipeline_is_a_hard_error(test_db):
    p = db.create_pipeline(name="dryrun-empty")
    result = dry_run_pipeline(p.id)
    assert not result.success
    assert "aucune étape" in result.errors[0]


def test_missing_pipeline_is_a_hard_error(test_db):
    result = dry_run_pipeline(999999)
    assert not result.success
    assert result.errors


def test_uses_graph_validation_when_edges_exist(test_db):
    """Même bascule linéaire/graphe que run_pipeline() (db.get_edges() non vide -> graphe) —
    ici un cycle doit être détecté par validate_pipeline_graph(), pas validate_step_sequence()."""
    p = db.create_pipeline(name="dryrun-graph-cycle")
    key_a, key_b = "step-a", "step-b"
    steps = [
        {"step_type": "LOCAL_COPY", "config": {"_step_key": key_a}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": key_b}},
    ]
    edges = [
        {"from_step_key": key_a, "from_port": "output_file", "to_step_key": key_b, "to_port": "input"},
        {"from_step_key": key_b, "from_port": "output_file", "to_step_key": key_a, "to_port": "input"},
    ]
    db.save_pipeline_graph(p.id, steps, edges)

    result = dry_run_pipeline(p.id, test_connections=False)
    assert not result.success
    assert any("cycle" in e for e in result.errors)
