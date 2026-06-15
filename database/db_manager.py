"""
DataScheduler — Gestionnaire SQLite
Fournit :
  - l'initialisation de la base
  - un context manager de session
  - des helpers CRUD pour chaque entité
"""

import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, joinedload

from .models import Base, OracleProfile, FtpProfile, SqlQuery, Pipeline, PipelineRun, PipelineStep, StepType


# ──────────────────────────────────────────────
#  CHEMIN DE LA BASE
# ──────────────────────────────────────────────

def get_db_path() -> Path:
    """
    Place la base dans %APPDATA%/DataScheduler/ sous Windows,
    ou ~/.DataScheduler/ sous Linux/Mac.
    """
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home())) / "DataScheduler"
    else:
        base = Path.home() / ".DataScheduler"
    base.mkdir(parents=True, exist_ok=True)
    return base / "datascheduler.db"


# ──────────────────────────────────────────────
#  ENGINE & SESSION FACTORY
# ──────────────────────────────────────────────

_engine = None
_SessionFactory = None


def _migrate(engine) -> None:
    """Applique les migrations DDL manquantes sur une base existante."""
    from sqlalchemy import text
    with engine.connect() as conn:
        oracle_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(oracle_profiles)")).fetchall()}
        if "auth_mode" not in oracle_cols:
            conn.execute(text(
                "ALTER TABLE oracle_profiles ADD COLUMN auth_mode VARCHAR(20) NOT NULL DEFAULT 'DEFAULT'"
            ))
            conn.commit()

        pipeline_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(pipelines)")).fetchall()}
        if "csv_quoting" not in pipeline_cols:
            conn.execute(text(
                "ALTER TABLE pipelines ADD COLUMN csv_quoting VARCHAR(20) NOT NULL DEFAULT 'QUOTE_NONNUMERIC'"
            ))
            conn.commit()

        # Création de la table pipeline_steps si absente
        tables = {r[0] for r in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        ).fetchall()}
        if "pipeline_steps" not in tables:
            conn.execute(text("""
                CREATE TABLE pipeline_steps (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    pipeline_id INTEGER NOT NULL REFERENCES pipelines(id),
                    step_order  INTEGER NOT NULL DEFAULT 0,
                    step_type   VARCHAR(30) NOT NULL,
                    label       VARCHAR(100),
                    config_json TEXT NOT NULL DEFAULT '{}'
                )
            """))
            conn.commit()


def init_db(db_path: Path = None) -> None:
    """Initialise le moteur et crée les tables si elles n'existent pas."""
    global _engine, _SessionFactory

    path = db_path or get_db_path()
    _engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},  # obligatoire pour SQLite + threads
        echo=False,
    )
    Base.metadata.create_all(_engine)
    _migrate(_engine)
    _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False)
    _migrate_legacy_pipelines()


@contextmanager
def get_session() -> Session:
    """Context manager — usage :  with get_session() as s: ..."""
    if _SessionFactory is None:
        raise RuntimeError("Base non initialisée. Appelle init_db() au démarrage.")
    session: Session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ──────────────────────────────────────────────
#  HELPERS ORACLE PROFILE
# ──────────────────────────────────────────────

def create_oracle_profile(name, host, port, username, password,
                           service_name=None, sid=None,
                           auth_mode="DEFAULT") -> OracleProfile:
    with get_session() as s:
        profile = OracleProfile(
            name=name, host=host, port=port,
            username=username, password=password,
            service_name=service_name, sid=sid,
            auth_mode=auth_mode,
        )
        s.add(profile)
    return profile


def get_oracle_profiles() -> list[OracleProfile]:
    with get_session() as s:
        return s.query(OracleProfile).order_by(OracleProfile.name).all()


def get_oracle_profile(profile_id: int) -> OracleProfile | None:
    with get_session() as s:
        return s.get(OracleProfile, profile_id)


def delete_oracle_profile(profile_id: int) -> bool:
    with get_session() as s:
        obj = s.get(OracleProfile, profile_id)
        if obj:
            s.delete(obj)
            return True
    return False


# ──────────────────────────────────────────────
#  HELPERS FTP PROFILE
# ──────────────────────────────────────────────

def create_ftp_profile(name, host, port, username, password, protocol="FTP") -> FtpProfile:
    with get_session() as s:
        profile = FtpProfile(
            name=name, host=host, port=port,
            username=username, password=password,
            protocol=protocol,
        )
        s.add(profile)
    return profile


def get_ftp_profiles() -> list[FtpProfile]:
    with get_session() as s:
        return s.query(FtpProfile).order_by(FtpProfile.name).all()


def get_ftp_profile(profile_id: int) -> FtpProfile | None:
    with get_session() as s:
        return s.get(FtpProfile, profile_id)


def delete_ftp_profile(profile_id: int) -> bool:
    with get_session() as s:
        obj = s.get(FtpProfile, profile_id)
        if obj:
            s.delete(obj)
            return True
    return False


# ──────────────────────────────────────────────
#  HELPERS SQL QUERY
# ──────────────────────────────────────────────

def create_sql_query(name, sql_text, description=None, oracle_profile_id=None) -> SqlQuery:
    with get_session() as s:
        q = SqlQuery(
            name=name, sql_text=sql_text,
            description=description,
            oracle_profile_id=oracle_profile_id,
        )
        s.add(q)
    return q


def get_sql_queries() -> list[SqlQuery]:
    with get_session() as s:
        return (s.query(SqlQuery)
                  .options(joinedload(SqlQuery.oracle_profile))
                  .order_by(SqlQuery.name)
                  .all())


def get_sql_query(query_id: int) -> SqlQuery | None:
    with get_session() as s:
        return s.get(SqlQuery, query_id)


def delete_sql_query(query_id: int) -> bool:
    with get_session() as s:
        obj = s.get(SqlQuery, query_id)
        if obj:
            s.delete(obj)
            return True
    return False


# ──────────────────────────────────────────────
#  HELPERS PIPELINE
# ──────────────────────────────────────────────

def create_pipeline(name, description=None,
                    frequency="DAILY", cron_expression=None,
                    scheduled_time="06:00", scheduled_day=None,
                    # Champs legacy conservés pour compatibilité migration
                    oracle_profile_id=None, sql_query_id=None, ftp_profile_id=None,
                    remote_path_tpl=None, filename_tpl=None,
                    csv_separator=";", csv_encoding="utf-8", csv_chunk_size=50000,
                    csv_quoting="QUOTE_NONNUMERIC") -> Pipeline:
    with get_session() as s:
        p = Pipeline(
            name=name, description=description,
            oracle_profile_id=oracle_profile_id,
            sql_query_id=sql_query_id,
            ftp_profile_id=ftp_profile_id,
            remote_path_tpl=remote_path_tpl,
            filename_tpl=filename_tpl,
            csv_separator=csv_separator,
            csv_encoding=csv_encoding,
            csv_chunk_size=csv_chunk_size,
            csv_quoting=csv_quoting,
            frequency=frequency,
            cron_expression=cron_expression,
            scheduled_time=scheduled_time,
            scheduled_day=scheduled_day,
        )
        s.add(p)
    return p


def get_pipelines(active_only=False) -> list[Pipeline]:
    with get_session() as s:
        q = (s.query(Pipeline)
               .options(
                   joinedload(Pipeline.oracle_profile),
                   joinedload(Pipeline.ftp_profile),
                   joinedload(Pipeline.sql_query),
                   joinedload(Pipeline.steps),
               )
               .order_by(Pipeline.name))
        if active_only:
            q = q.filter(Pipeline.is_active.is_(True))
        return q.all()


def get_pipeline(pipeline_id: int) -> Pipeline | None:
    with get_session() as s:
        return s.get(Pipeline, pipeline_id)


def set_pipeline_active(pipeline_id: int, active: bool) -> bool:
    with get_session() as s:
        obj = s.get(Pipeline, pipeline_id)
        if obj:
            obj.is_active = active
            return True
    return False


def delete_pipeline(pipeline_id: int) -> bool:
    with get_session() as s:
        obj = s.get(Pipeline, pipeline_id)
        if obj:
            s.delete(obj)
            return True
    return False


# ──────────────────────────────────────────────
#  HELPERS PIPELINE RUN (historique)
# ──────────────────────────────────────────────

def create_run(pipeline_id: int) -> PipelineRun:
    with get_session() as s:
        run = PipelineRun(pipeline_id=pipeline_id)
        s.add(run)
    return run


def finish_run(run_id: int, status: str, rows_exported=None,
               remote_path=None, error_message=None, log_text=None) -> bool:
    from datetime import datetime
    with get_session() as s:
        run = s.get(PipelineRun, run_id)
        if not run:
            return False
        run.finished_at   = datetime.utcnow()
        run.status        = status
        run.rows_exported = rows_exported
        run.remote_path   = remote_path
        run.error_message = error_message
        run.log_text      = log_text
        return True


def get_runs(pipeline_id: int, limit: int = 50) -> list[PipelineRun]:
    with get_session() as s:
        return (
            s.query(PipelineRun)
            .options(joinedload(PipelineRun.pipeline))
            .filter(PipelineRun.pipeline_id == pipeline_id)
            .order_by(PipelineRun.started_at.desc())
            .limit(limit)
            .all()
        )


def get_recent_runs(limit: int = 100) -> list[PipelineRun]:
    with get_session() as s:
        return (
            s.query(PipelineRun)
            .options(joinedload(PipelineRun.pipeline))
            .order_by(PipelineRun.started_at.desc())
            .limit(limit)
            .all()
        )


# ──────────────────────────────────────────────
#  HELPERS PIPELINE STEPS
# ──────────────────────────────────────────────

def get_steps(pipeline_id: int) -> list[PipelineStep]:
    with get_session() as s:
        return (s.query(PipelineStep)
                  .filter_by(pipeline_id=pipeline_id)
                  .order_by(PipelineStep.step_order)
                  .all())


def save_steps(pipeline_id: int, steps: list[dict]) -> None:
    """Remplace toutes les étapes d'un pipeline.

    Chaque dict : {"step_type": str, "label": str|None, "config": dict}
    """
    import json
    with get_session() as s:
        s.query(PipelineStep).filter_by(pipeline_id=pipeline_id).delete()
        for i, step in enumerate(steps):
            s.add(PipelineStep(
                pipeline_id=pipeline_id,
                step_order=i,
                step_type=step["step_type"],
                label=step.get("label"),
                config_json=json.dumps(step.get("config", {})),
            ))


# ──────────────────────────────────────────────
#  MIGRATION LEGACY → STEPS
# ──────────────────────────────────────────────

def _migrate_legacy_pipelines() -> None:
    """Convertit les anciens pipelines Oracle→FTP en étapes PipelineStep."""
    import json
    if _SessionFactory is None:
        return
    with get_session() as s:
        pipelines = s.query(Pipeline).all()
        for p in pipelines:
            has_steps = s.query(PipelineStep).filter_by(pipeline_id=p.id).count() > 0
            if has_steps:
                continue
            if not (p.oracle_profile_id and p.sql_query_id and p.ftp_profile_id):
                continue
            s.add(PipelineStep(
                pipeline_id=p.id,
                step_order=0,
                step_type=StepType.ORACLE_EXTRACT,
                label="Extraction Oracle",
                config_json=json.dumps({
                    "oracle_profile_id": p.oracle_profile_id,
                    "sql_query_id":      p.sql_query_id,
                    "csv_separator":     p.csv_separator or ";",
                    "csv_encoding":      p.csv_encoding  or "utf-8-sig",
                    "csv_chunk_size":    p.csv_chunk_size or 50000,
                    "csv_quoting":       p.csv_quoting    or "QUOTE_NONNUMERIC",
                }),
            ))
            s.add(PipelineStep(
                pipeline_id=p.id,
                step_order=1,
                step_type=StepType.FTP_UPLOAD,
                label="Envoi FTP",
                config_json=json.dumps({
                    "ftp_profile_id":  p.ftp_profile_id,
                    "remote_path_tpl": p.remote_path_tpl or "/export/",
                    "filename_tpl":    p.filename_tpl    or "export_{yyyyMMdd}.csv",
                }),
            ))