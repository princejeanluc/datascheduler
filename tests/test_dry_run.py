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


def _spark_sql_profiles():
    edge = db.create_ssh_profile(name="EDGE01", host="127.0.0.1", port=22, username="u", password="p")
    krb = db.create_kerberos_profile(name="KRB1", principal="u@REALM", password="p")
    query = db.create_sql_query(name="Q1", sql_text="SELECT 1")
    return edge, krb, query


def test_spark_sql_missing_edge_profile_is_a_hard_error(test_db):
    _, krb, query = _spark_sql_profiles()
    p = db.create_pipeline(name="dryrun-spark-missing-edge")
    db.save_steps(p.id, [{
        "step_type": "SPARK_SQL",
        "config": {"edge_profile_id": 999999, "kerberos_profile_id": krb.id, "sql_query_id": query.id},
    }])

    result = dry_run_pipeline(p.id, test_connections=False)
    assert not result.success
    assert any("n'existe plus" in e for e in result.errors)


def test_spark_sql_missing_kerberos_profile_is_a_hard_error(test_db):
    edge, _, query = _spark_sql_profiles()
    p = db.create_pipeline(name="dryrun-spark-missing-krb")
    db.save_steps(p.id, [{
        "step_type": "SPARK_SQL",
        "config": {"edge_profile_id": edge.id, "kerberos_profile_id": 999999, "sql_query_id": query.id},
    }])

    result = dry_run_pipeline(p.id, test_connections=False)
    assert not result.success
    assert any("n'existe plus" in e for e in result.errors)


def test_spark_sql_connection_failures_are_warnings_not_errors(test_db):
    edge, krb, query = _spark_sql_profiles()
    p = db.create_pipeline(name="dryrun-spark-conn-fail")
    db.save_steps(p.id, [{
        "step_type": "SPARK_SQL",
        "config": {"edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "sql_query_id": query.id},
    }])

    result = dry_run_pipeline(p.id, test_connections=True)
    assert result.success   # avertissements seulement — ni le SSH ni le kinit ne peuvent réussir ici
    # 2 connexions testées (edge_profile + kerberos_profile) — sql_query n'est jamais compté.
    assert result.checked_connections == 2
    assert len(result.warnings) == 2
    assert any("edge_profile" in w for w in result.warnings)
    assert any("kerberos_profile" in w for w in result.warnings)


def test_spark_sql_kerberos_test_uses_sibling_edge_profile(test_db, monkeypatch):
    """Le test Kerberos n'a de sens qu'avec un profil SSH — il doit résoudre edge_profile_id
    depuis la même étape plutôt que rester silencieusement no-op."""
    edge, krb, query = _spark_sql_profiles()
    p = db.create_pipeline(name="dryrun-spark-krb-uses-edge")
    db.save_steps(p.id, [{
        "step_type": "SPARK_SQL",
        "config": {"edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "sql_query_id": query.id},
    }])

    captured = {}
    import core.spark as spark_module

    def fake_test_kerberos_auth(ssh_cfg, krb_cfg):
        captured["ssh_cfg"] = ssh_cfg
        captured["krb_cfg"] = krb_cfg
        return spark_module.ConnectionTestResult(True, "OK (mock)")

    monkeypatch.setattr(spark_module, "test_kerberos_auth", fake_test_kerberos_auth)

    result = dry_run_pipeline(p.id, test_connections=True)
    assert captured["ssh_cfg"].host == "127.0.0.1"
    assert captured["krb_cfg"].principal == "u@REALM"
    # Le test Kerberos a réussi (mocké) ; seul le SSH direct échoue encore réellement.
    assert result.checked_connections == 2
    assert len(result.warnings) == 1


def test_spark_sql_kerberos_test_fails_cleanly_without_sibling_edge_profile(test_db):
    """edge_profile_id absent de la config (jamais renseigné) -> avertissement clair, pas de
    crash — même si la validation de forme laisse passer (kerberos_profile_id est bien résolu,
    c'est edge_profile_id qui manque)."""
    _, krb, query = _spark_sql_profiles()
    p = db.create_pipeline(name="dryrun-spark-krb-no-edge")
    db.save_steps(p.id, [{
        "step_type": "SPARK_SQL",
        "config": {"kerberos_profile_id": krb.id, "sql_query_id": query.id},
    }])

    result = dry_run_pipeline(p.id, test_connections=True)
    assert result.success
    assert any("Aucun profil SSH configuré" in w for w in result.warnings)


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
