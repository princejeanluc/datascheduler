"""
test_db.py — Vérifie que les modèles et la DB fonctionnent correctement.
Lance avec : python test_db.py
"""

import sys
from pathlib import Path

# Ajouter le dossier parent au path pour l'import
sys.path.insert(0, str(Path(__file__).parent.parent))

from DataScheduler.database.db_manager import (
    init_db,
    create_oracle_profile, get_oracle_profiles,
    create_ftp_profile,    get_ftp_profiles,
    create_sql_query,      get_sql_queries,
    create_pipeline,       get_pipelines,
    create_run,            finish_run, get_runs,
)

# ── Init base en mémoire (test uniquement) ──
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from DataScheduler.database.models import Base
import DataScheduler.database.db_manager as _dbm

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
Base.metadata.create_all(engine)
_dbm._engine = engine
_dbm._SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)


def test_oracle_profile():
    p = create_oracle_profile(
        name="ORACLE_PROD", host="10.10.1.15", port=1521,
        username="reporting", password="secret",
        service_name="PROD"
    )
    profiles = get_oracle_profiles()
    assert len(profiles) == 1
    assert profiles[0].name == "ORACLE_PROD"
    print("✅  OracleProfile OK")
    return profiles[0].id


def test_ftp_profile():
    p = create_ftp_profile(
        name="FTP_FINANCE", host="ftp.company.com", port=21,
        username="ftpuser", password="ftppass", protocol="FTPS"
    )
    profiles = get_ftp_profiles()
    assert len(profiles) == 1
    assert profiles[0].protocol == "FTPS"
    print("✅  FtpProfile OK")
    return profiles[0].id


def test_sql_query(oracle_id):
    q = create_sql_query(
        name="REQUETE_VENTES_JOUR",
        sql_text="SELECT * FROM sales WHERE sale_date >= TRUNC(SYSDATE)-1",
        description="Ventes de la veille",
        oracle_profile_id=oracle_id
    )
    queries = get_sql_queries()
    assert len(queries) == 1
    print("✅  SqlQuery OK")
    return queries[0].id


def test_pipeline(oracle_id, ftp_id, query_id):
    p = create_pipeline(
        name="EXPORT_VENTES_QUOTIDIEN",
        oracle_profile_id=oracle_id,
        sql_query_id=query_id,
        ftp_profile_id=ftp_id,
        remote_path_tpl="/export/finance/{yyyy}/{MM}/",
        filename_tpl="ventes_{yyyyMMdd}.csv",
        frequency="DAILY",
        scheduled_time="06:00",
    )
    pipelines = get_pipelines()
    assert len(pipelines) == 1
    assert pipelines[0].filename_tpl == "ventes_{yyyyMMdd}.csv"
    print("✅  Pipeline OK")
    return pipelines[0].id


def test_run(pipeline_id):
    run = create_run(pipeline_id)
    assert run.id is not None

    ok = finish_run(
        run.id,
        status="SUCCESS",
        rows_exported=2_435_612,
        remote_path="/export/finance/2026/06/ventes_20260608.csv",
        log_text="Connexion OK\nRequête OK\nExport OK\nUpload OK",
    )
    assert ok

    runs = get_runs(pipeline_id)
    assert len(runs) == 1
    assert runs[0].rows_exported == 2_435_612
    assert runs[0].duration_seconds is not None
    print("✅  PipelineRun OK")


if __name__ == "__main__":
    print("\n🔧  Test de la base DataScheduler\n")
    oracle_id = test_oracle_profile()
    ftp_id    = test_ftp_profile()
    query_id  = test_sql_query(oracle_id)
    pipe_id   = test_pipeline(oracle_id, ftp_id, query_id)
    test_run(pipe_id)
    print("\n🎉  Tous les tests passent !\n")