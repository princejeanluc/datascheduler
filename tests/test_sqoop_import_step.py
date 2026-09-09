"""
DataScheduler — tests/test_sqoop_import_step.py
Vérifie SqoopImportStep.run() — miroir de test_sqoop_export_step.py dans l'autre sens.
core.sqoop.run_sqoop_import est monkeypatché directement (pas besoin de redescendre jusqu'aux
fakes paramiko, déjà couverts par tests/test_sqoop_run.py) : résolution des 4 références,
résolution des jetons dans les champs de table, la validation "mappers > 1 exige split_by_column"
propre à cette étape, succès/échec, et absence du mot de passe Oracle en clair dans les logs.
"""

import core.sqoop as sqoop_module
from core.steps.base import StepContext
from core.steps.sqoop_import import SqoopImportStep


class _FakeSqoopCommandResult:
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


def _elevation_profile():
    from database import db_manager as db
    return db.create_elevation_profile(name="NIFI", target_user="nifi", password="sharedpw")


def test_success(test_db, monkeypatch):
    edge, krb, oracle = _base_profiles()

    def fake_run_sqoop_import(ssh_cfg, krb_cfg, oracle_cfg, oracle_table, hcatalog_database,
                               hcatalog_table, num_mappers, split_by_column, sqoop_conf,
                               timeout=3600, elevation_cfg=None, on_progress=None, cancel_event=None):
        return _FakeSqoopCommandResult(success=True)

    monkeypatch.setattr(sqoop_module, "run_sqoop_import", fake_run_sqoop_import)

    step = SqoopImportStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "oracle_profile_id": oracle.id,
        "oracle_table": "xxx.xxxxx", "hcatalog_database": "DD",
        "hcatalog_table": "FINAL_EQUIPEMENT_CLIENT",
    })
    result = step.run(StepContext())

    assert result.success, result.error


def test_resolves_tokens_in_table_fields(test_db, monkeypatch):
    edge, krb, oracle = _base_profiles()
    captured = {}

    def fake_run_sqoop_import(ssh_cfg, krb_cfg, oracle_cfg, oracle_table, hcatalog_database,
                               hcatalog_table, num_mappers, split_by_column, sqoop_conf,
                               timeout=3600, elevation_cfg=None, on_progress=None, cancel_event=None):
        captured["oracle_table"] = oracle_table
        captured["hcatalog_database"] = hcatalog_database
        captured["hcatalog_table"] = hcatalog_table
        return _FakeSqoopCommandResult(success=True)

    monkeypatch.setattr(sqoop_module, "run_sqoop_import", fake_run_sqoop_import)

    step = SqoopImportStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "oracle_profile_id": oracle.id,
        "oracle_table": "xxx.T_{dd}", "hcatalog_database": "DD_{yyyy}", "hcatalog_table": "T_{MM}",
    })
    step.run(StepContext())

    from datetime import datetime
    now = datetime.now()
    assert captured["oracle_table"] == f"xxx.T_{now:%d}"
    assert captured["hcatalog_database"] == f"DD_{now:%Y}"
    assert captured["hcatalog_table"] == f"T_{now:%m}"


def test_missing_edge_profile_fails_cleanly(test_db):
    _, krb, oracle = _base_profiles()
    step = SqoopImportStep({
        "edge_profile_id": 999999, "kerberos_profile_id": krb.id, "oracle_profile_id": oracle.id,
        "oracle_table": "xxx.t", "hcatalog_database": "DD", "hcatalog_table": "T",
    })
    result = step.run(StepContext())
    assert result.success is False
    assert "SSH" in result.error


def test_missing_kerberos_profile_fails_cleanly(test_db):
    edge, _, oracle = _base_profiles()
    step = SqoopImportStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": 999999, "oracle_profile_id": oracle.id,
        "oracle_table": "xxx.t", "hcatalog_database": "DD", "hcatalog_table": "T",
    })
    result = step.run(StepContext())
    assert result.success is False
    assert "Kerberos" in result.error


def test_missing_oracle_profile_fails_cleanly(test_db):
    edge, krb, _ = _base_profiles()
    step = SqoopImportStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "oracle_profile_id": 999999,
        "oracle_table": "xxx.t", "hcatalog_database": "DD", "hcatalog_table": "T",
    })
    result = step.run(StepContext())
    assert result.success is False
    assert "Oracle" in result.error


def test_missing_elevation_profile_fails_cleanly(test_db):
    edge, krb, oracle = _base_profiles()
    step = SqoopImportStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "oracle_profile_id": oracle.id,
        "elevation_profile_id": 999999,
        "oracle_table": "xxx.t", "hcatalog_database": "DD", "hcatalog_table": "T",
    })
    result = step.run(StepContext())
    assert result.success is False
    assert "élévation" in result.error


def test_kerberos_optional_is_skipped_when_not_configured(test_db, monkeypatch):
    edge, _krb, oracle = _base_profiles()
    captured = {}

    def fake_run_sqoop_import(ssh_cfg, krb_cfg, oracle_cfg, oracle_table, hcatalog_database,
                               hcatalog_table, num_mappers, split_by_column, sqoop_conf,
                               timeout=3600, elevation_cfg=None, on_progress=None, cancel_event=None):
        captured["krb_cfg"] = krb_cfg
        return _FakeSqoopCommandResult(success=True)

    monkeypatch.setattr(sqoop_module, "run_sqoop_import", fake_run_sqoop_import)

    step = SqoopImportStep({
        "edge_profile_id": edge.id, "oracle_profile_id": oracle.id,   # pas de kerberos_profile_id
        "oracle_table": "xxx.t", "hcatalog_database": "DD", "hcatalog_table": "T",
    })
    result = step.run(StepContext())

    assert result.success, result.error
    assert captured["krb_cfg"] is None


def test_elevation_profile_is_resolved_and_passed_through(test_db, monkeypatch):
    edge, _krb, oracle = _base_profiles()
    elevation = _elevation_profile()
    captured = {}

    def fake_run_sqoop_import(ssh_cfg, krb_cfg, oracle_cfg, oracle_table, hcatalog_database,
                               hcatalog_table, num_mappers, split_by_column, sqoop_conf,
                               timeout=3600, elevation_cfg=None, on_progress=None, cancel_event=None):
        captured["elevation_cfg"] = elevation_cfg
        return _FakeSqoopCommandResult(success=True)

    monkeypatch.setattr(sqoop_module, "run_sqoop_import", fake_run_sqoop_import)

    step = SqoopImportStep({
        "edge_profile_id": edge.id, "oracle_profile_id": oracle.id,
        "elevation_profile_id": elevation.id,
        "oracle_table": "xxx.t", "hcatalog_database": "DD", "hcatalog_table": "T",
    })
    result = step.run(StepContext())

    assert result.success, result.error
    assert captured["elevation_cfg"].target_user == "nifi"


def test_failure_propagates_error_message(test_db, monkeypatch):
    edge, krb, oracle = _base_profiles()

    def fake_run_sqoop_import(ssh_cfg, krb_cfg, oracle_cfg, oracle_table, hcatalog_database,
                               hcatalog_table, num_mappers, split_by_column, sqoop_conf,
                               timeout=3600, elevation_cfg=None, on_progress=None, cancel_event=None):
        return _FakeSqoopCommandResult(success=False, error="sqoop import a échoué")

    monkeypatch.setattr(sqoop_module, "run_sqoop_import", fake_run_sqoop_import)

    step = SqoopImportStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "oracle_profile_id": oracle.id,
        "oracle_table": "xxx.t", "hcatalog_database": "DD", "hcatalog_table": "T",
    })
    result = step.run(StepContext())

    assert result.success is False
    assert result.error == "sqoop import a échoué"


def test_password_never_appears_in_context_logs(test_db, monkeypatch):
    edge, krb, oracle = _base_profiles()

    def fake_run_sqoop_import(ssh_cfg, krb_cfg, oracle_cfg, oracle_table, hcatalog_database,
                               hcatalog_table, num_mappers, split_by_column, sqoop_conf,
                               timeout=3600, elevation_cfg=None, on_progress=None, cancel_event=None):
        return _FakeSqoopCommandResult(success=True)

    monkeypatch.setattr(sqoop_module, "run_sqoop_import", fake_run_sqoop_import)

    step = SqoopImportStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "oracle_profile_id": oracle.id,
        "oracle_table": "xxx.t", "hcatalog_database": "DD", "hcatalog_table": "T",
    })
    ctx = StepContext()
    step.run(ctx)

    for line in ctx.log_lines:
        assert "s3cr3t" not in line


# ── Validation propre à SQOOP_IMPORT : mappers > 1 exige split_by_column ──────────

def test_multiple_mappers_without_split_by_fails_cleanly_without_calling_sqoop(test_db, monkeypatch):
    edge, krb, oracle = _base_profiles()
    called = []
    monkeypatch.setattr(sqoop_module, "run_sqoop_import", lambda *a, **kw: called.append(1))

    step = SqoopImportStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "oracle_profile_id": oracle.id,
        "oracle_table": "xxx.t", "hcatalog_database": "DD", "hcatalog_table": "T",
        "num_mappers": 4,   # pas de split_by_column
    })
    result = step.run(StepContext())

    assert result.success is False
    assert "partitionnement" in result.error
    assert called == []   # jamais tenté d'exécuter sqoop sans split-by valide


def test_multiple_mappers_with_split_by_succeeds(test_db, monkeypatch):
    edge, krb, oracle = _base_profiles()
    captured = {}

    def fake_run_sqoop_import(ssh_cfg, krb_cfg, oracle_cfg, oracle_table, hcatalog_database,
                               hcatalog_table, num_mappers, split_by_column, sqoop_conf,
                               timeout=3600, elevation_cfg=None, on_progress=None, cancel_event=None):
        captured["num_mappers"] = num_mappers
        captured["split_by_column"] = split_by_column
        return _FakeSqoopCommandResult(success=True)

    monkeypatch.setattr(sqoop_module, "run_sqoop_import", fake_run_sqoop_import)

    step = SqoopImportStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "oracle_profile_id": oracle.id,
        "oracle_table": "xxx.t", "hcatalog_database": "DD", "hcatalog_table": "T",
        "num_mappers": 4, "split_by_column": "ID_CLIENT",
    })
    result = step.run(StepContext())

    assert result.success, result.error
    assert captured["num_mappers"] == 4
    assert captured["split_by_column"] == "ID_CLIENT"


def test_default_num_mappers_is_one_when_not_configured(test_db, monkeypatch):
    """Zéro changement requis pour une étape qui ne se soucie pas de la parallélisation —
    fonctionne sans le champ du tout."""
    edge, krb, oracle = _base_profiles()
    captured = {}

    def fake_run_sqoop_import(ssh_cfg, krb_cfg, oracle_cfg, oracle_table, hcatalog_database,
                               hcatalog_table, num_mappers, split_by_column, sqoop_conf,
                               timeout=3600, elevation_cfg=None, on_progress=None, cancel_event=None):
        captured["num_mappers"] = num_mappers
        return _FakeSqoopCommandResult(success=True)

    monkeypatch.setattr(sqoop_module, "run_sqoop_import", fake_run_sqoop_import)

    step = SqoopImportStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "oracle_profile_id": oracle.id,
        "oracle_table": "xxx.t", "hcatalog_database": "DD", "hcatalog_table": "T",
    })
    result = step.run(StepContext())

    assert result.success, result.error
    assert captured["num_mappers"] == 1
