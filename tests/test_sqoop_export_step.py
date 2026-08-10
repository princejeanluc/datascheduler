"""
DataScheduler — tests/test_sqoop_export_step.py
Vérifie SqoopExportStep.run() (chantier K) — core.sqoop.run_sqoop_export est monkeypatché
directement (pas besoin de redescendre jusqu'aux fakes paramiko, déjà couverts par
tests/test_sqoop_run.py) : résolution des 3 références, résolution des jetons dans les champs
de table, succès/échec, et absence du mot de passe Oracle en clair dans les logs.
"""

import core.sqoop as sqoop_module
from core.steps.base import StepContext
from core.steps.sqoop_export import SqoopExportStep


class _FakeSqoopExportResult:
    def __init__(self, success=True, error="", duration_s=1.0):
        self.success = success
        self.error = error
        self.duration_s = duration_s


def _base_profiles():
    from database import db_manager as db
    edge   = db.create_ssh_profile(name="EDGE03", host="edge03", port=22, username="u", password="p")
    krb    = db.create_kerberos_profile(name="KRB1", principal="u@REALM", password="p")
    oracle = db.create_oracle_profile(name="ORA1", host="10.0.0.5", port=1521,
                                       username="ORAUSER", password="s3cr3t", service_name="PRODDB")
    return edge, krb, oracle


def test_success(test_db, monkeypatch):
    edge, krb, oracle = _base_profiles()

    def fake_run_sqoop_export(ssh_cfg, krb_cfg, oracle_cfg, hcatalog_database, hcatalog_table,
                               oracle_table, sqoop_conf, timeout=3600):
        return _FakeSqoopExportResult(success=True)

    monkeypatch.setattr(sqoop_module, "run_sqoop_export", fake_run_sqoop_export)

    step = SqoopExportStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "oracle_profile_id": oracle.id,
        "hcatalog_database": "DD", "hcatalog_table": "FINAL_EQUIPEMENT_CLIENT",
        "oracle_table": "xxx.xxxxx",
    })
    result = step.run(StepContext())

    assert result.success, result.error


def test_resolves_tokens_in_table_fields(test_db, monkeypatch):
    edge, krb, oracle = _base_profiles()

    captured = {}

    def fake_run_sqoop_export(ssh_cfg, krb_cfg, oracle_cfg, hcatalog_database, hcatalog_table,
                               oracle_table, sqoop_conf, timeout=3600):
        captured["hcatalog_database"] = hcatalog_database
        captured["hcatalog_table"] = hcatalog_table
        captured["oracle_table"] = oracle_table
        return _FakeSqoopExportResult(success=True)

    monkeypatch.setattr(sqoop_module, "run_sqoop_export", fake_run_sqoop_export)

    step = SqoopExportStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "oracle_profile_id": oracle.id,
        "hcatalog_database": "DD_{yyyy}", "hcatalog_table": "T_{MM}",
        "oracle_table": "xxx.T_{dd}",
    })
    step.run(StepContext())

    from datetime import datetime
    now = datetime.now()
    assert captured["hcatalog_database"] == f"DD_{now:%Y}"
    assert captured["hcatalog_table"] == f"T_{now:%m}"
    assert captured["oracle_table"] == f"xxx.T_{now:%d}"


def test_missing_edge_profile_fails_cleanly(test_db):
    _, krb, oracle = _base_profiles()
    step = SqoopExportStep({
        "edge_profile_id": 999999, "kerberos_profile_id": krb.id, "oracle_profile_id": oracle.id,
        "hcatalog_database": "DD", "hcatalog_table": "T", "oracle_table": "xxx.t",
    })
    result = step.run(StepContext())
    assert result.success is False
    assert "SSH" in result.error


def test_missing_kerberos_profile_fails_cleanly(test_db):
    edge, _, oracle = _base_profiles()
    step = SqoopExportStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": 999999, "oracle_profile_id": oracle.id,
        "hcatalog_database": "DD", "hcatalog_table": "T", "oracle_table": "xxx.t",
    })
    result = step.run(StepContext())
    assert result.success is False
    assert "Kerberos" in result.error


def test_missing_oracle_profile_fails_cleanly(test_db):
    edge, krb, _ = _base_profiles()
    step = SqoopExportStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "oracle_profile_id": 999999,
        "hcatalog_database": "DD", "hcatalog_table": "T", "oracle_table": "xxx.t",
    })
    result = step.run(StepContext())
    assert result.success is False
    assert "Oracle" in result.error


def test_failure_propagates_error_message(test_db, monkeypatch):
    edge, krb, oracle = _base_profiles()

    def fake_run_sqoop_export(ssh_cfg, krb_cfg, oracle_cfg, hcatalog_database, hcatalog_table,
                               oracle_table, sqoop_conf, timeout=3600):
        return _FakeSqoopExportResult(success=False, error="sqoop export a échoué")

    monkeypatch.setattr(sqoop_module, "run_sqoop_export", fake_run_sqoop_export)

    step = SqoopExportStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "oracle_profile_id": oracle.id,
        "hcatalog_database": "DD", "hcatalog_table": "T", "oracle_table": "xxx.t",
    })
    result = step.run(StepContext())

    assert result.success is False
    assert result.error == "sqoop export a échoué"


def test_password_never_appears_in_context_logs(test_db, monkeypatch):
    edge, krb, oracle = _base_profiles()

    def fake_run_sqoop_export(ssh_cfg, krb_cfg, oracle_cfg, hcatalog_database, hcatalog_table,
                               oracle_table, sqoop_conf, timeout=3600):
        return _FakeSqoopExportResult(success=True)

    monkeypatch.setattr(sqoop_module, "run_sqoop_export", fake_run_sqoop_export)

    step = SqoopExportStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "oracle_profile_id": oracle.id,
        "hcatalog_database": "DD", "hcatalog_table": "T", "oracle_table": "xxx.t",
    })
    ctx = StepContext()
    step.run(ctx)

    for line in ctx.log_lines:
        assert "s3cr3t" not in line
