"""
DataScheduler — tests/test_db_manager.py
Vérifie que les modèles et le CRUD de database/db_manager.py fonctionnent correctement.
"""

from database import crypto, db_manager as db


def test_oracle_profile(test_db):
    db.create_oracle_profile(
        name="ORACLE_PROD", host="10.10.1.15", port=1521,
        username="reporting", password="secret",
        service_name="PROD",
    )
    profiles = db.get_oracle_profiles()
    assert len(profiles) == 1
    assert profiles[0].name == "ORACLE_PROD"
    # Le mot de passe ne doit jamais être stocké en clair.
    assert profiles[0].password != "secret"
    assert crypto.decrypt(profiles[0].password) == "secret"


def test_oracle_profile_update_keeps_password_when_blank(test_db):
    created = db.create_oracle_profile(
        name="ORACLE_PROD", host="h1", port=1521,
        username="u", password="original_secret", service_name="PROD",
    )
    db.update_oracle_profile(
        created.id, name="ORACLE_PROD", host="h2", port=1521,
        username="u", password=None, service_name="PROD",
    )
    updated = db.get_oracle_profile(created.id)
    assert updated.host == "h2"
    assert crypto.decrypt(updated.password) == "original_secret"

    db.update_oracle_profile(
        created.id, name="ORACLE_PROD", host="h2", port=1521,
        username="u", password="new_secret", service_name="PROD",
    )
    updated = db.get_oracle_profile(created.id)
    assert crypto.decrypt(updated.password) == "new_secret"


def test_ftp_profile(test_db):
    db.create_ftp_profile(
        name="FTP_FINANCE", host="ftp.company.com", port=21,
        username="ftpuser", password="ftppass", protocol="FTPS",
    )
    profiles = db.get_ftp_profiles()
    assert len(profiles) == 1
    assert profiles[0].protocol == "FTPS"


def test_sql_query(test_db):
    oracle_id = db.create_oracle_profile(
        name="ORACLE_PROD", host="h", port=1521,
        username="u", password="p", service_name="PROD",
    ).id

    db.create_sql_query(
        name="REQUETE_VENTES_JOUR",
        sql_text="SELECT * FROM sales WHERE sale_date >= TRUNC(SYSDATE)-1",
        description="Ventes de la veille",
        oracle_profile_id=oracle_id,
    )
    queries = db.get_sql_queries()
    assert len(queries) == 1


def test_pipeline(test_db):
    oracle_id = db.create_oracle_profile(
        name="ORACLE_PROD", host="h", port=1521,
        username="u", password="p", service_name="PROD",
    ).id
    ftp_id = db.create_ftp_profile(
        name="FTP_FINANCE", host="ftp.company.com", port=21,
        username="ftpuser", password="ftppass", protocol="FTPS",
    ).id
    query_id = db.create_sql_query(
        name="REQUETE_VENTES_JOUR",
        sql_text="SELECT * FROM sales",
        oracle_profile_id=oracle_id,
    ).id

    db.create_pipeline(
        name="EXPORT_VENTES_QUOTIDIEN",
        oracle_profile_id=oracle_id,
        sql_query_id=query_id,
        ftp_profile_id=ftp_id,
        remote_path_tpl="/export/finance/{yyyy}/{MM}/",
        filename_tpl="ventes_{yyyyMMdd}.csv",
        frequency="DAILY",
        scheduled_time="06:00",
    )
    pipelines = db.get_pipelines()
    assert len(pipelines) == 1
    assert pipelines[0].filename_tpl == "ventes_{yyyyMMdd}.csv"


def test_run(test_db):
    pipeline_id = db.create_pipeline(name="EXPORT_VENTES_QUOTIDIEN").id

    run = db.create_run(pipeline_id)
    assert run.id is not None

    ok = db.finish_run(
        run.id,
        status="SUCCESS",
        rows_exported=2_435_612,
        remote_path="/export/finance/2026/06/ventes_20260608.csv",
        log_text="Connexion OK\nRequête OK\nExport OK\nUpload OK",
    )
    assert ok

    runs = db.get_runs(pipeline_id)
    assert len(runs) == 1
    assert runs[0].rows_exported == 2_435_612
    assert runs[0].duration_seconds is not None
