"""
DataScheduler — Gestionnaire SQLite
Fournit :
  - l'initialisation de la base
  - un context manager de session
  - des helpers CRUD pour chaque entité
"""

import os
import uuid
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, joinedload

from . import crypto
from .models import Base, OracleProfile, FtpProfile, SmtpProfile, DatabaseProfile, DbType, SqlQuery, Pipeline, PipelineRun, PipelineStep, PipelineEdge, StepType, NotificationSettings, AuditEvent, SshProfile, KerberosProfile


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

        # Création de la table smtp_profiles si absente
        if "smtp_profiles" not in tables:
            conn.execute(text("""
                CREATE TABLE smtp_profiles (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    name         VARCHAR(100) NOT NULL UNIQUE,
                    host         VARCHAR(255) NOT NULL,
                    port         INTEGER NOT NULL DEFAULT 587,
                    username     VARCHAR(100),
                    password     VARCHAR(255),
                    use_tls      BOOLEAN NOT NULL DEFAULT 1,
                    from_address VARCHAR(255) NOT NULL,
                    created_at   DATETIME,
                    updated_at   DATETIME
                )
            """))
            conn.commit()

        # Création de la table database_profiles si absente (MySQL/PostgreSQL/SQL Server)
        if "database_profiles" not in tables:
            conn.execute(text("""
                CREATE TABLE database_profiles (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    name          VARCHAR(100) NOT NULL UNIQUE,
                    db_type       VARCHAR(20) NOT NULL,
                    host          VARCHAR(255) NOT NULL,
                    port          INTEGER NOT NULL,
                    username      VARCHAR(100) NOT NULL,
                    password      VARCHAR(255) NOT NULL,
                    database_name VARCHAR(100),
                    extra_json    TEXT NOT NULL DEFAULT '{}',
                    created_at    DATETIME,
                    updated_at    DATETIME
                )
            """))
            conn.commit()

        # Colonnes pour le verrou anti-chevauchement et l'exécuteur restructuré
        pipeline_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(pipelines)")).fetchall()}
        if "prevent_overlap" not in pipeline_cols:
            conn.execute(text(
                "ALTER TABLE pipelines ADD COLUMN prevent_overlap BOOLEAN NOT NULL DEFAULT 0"
            ))
            conn.commit()

        step_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(pipeline_steps)")).fetchall()}
        if "retry_count" not in step_cols:
            conn.execute(text(
                "ALTER TABLE pipeline_steps ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0"
            ))
            conn.commit()
        if "run_always" not in step_cols:
            conn.execute(text(
                "ALTER TABLE pipeline_steps ADD COLUMN run_always BOOLEAN NOT NULL DEFAULT 0"
            ))
            conn.commit()
        # Position sur le canevas (chantier 6a/6b) — DEFAULT 0 constant pour toutes les lignes,
        # pas besoin d'un backfill ligne par ligne comme pour uuid (valeurs devant être distinctes).
        for col in ("pos_x", "pos_y"):
            if col not in step_cols:
                conn.execute(text(
                    f"ALTER TABLE pipeline_steps ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0"
                ))
                conn.commit()

        # Rendre oracle_profile_id / sql_query_id / ftp_profile_id / remote_path_tpl / filename_tpl
        # nullable (requis par l'architecture flexible à base d'étapes).
        # SQLite ne supporte pas ALTER COLUMN : on reconstruit la table si nécessaire.
        pipeline_info = {r[1]: r[3] for r in conn.execute(
            text("PRAGMA table_info(pipelines)")
        ).fetchall()}  # {col_name: notnull}
        needs_rebuild = any(
            pipeline_info.get(col, 0) == 1
            for col in ("oracle_profile_id", "sql_query_id", "ftp_profile_id",
                        "remote_path_tpl", "filename_tpl")
        )
        if needs_rebuild:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.execute(text("""
                CREATE TABLE pipelines_new (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    name              VARCHAR(100) NOT NULL UNIQUE,
                    description       TEXT,
                    oracle_profile_id INTEGER REFERENCES oracle_profiles(id),
                    sql_query_id      INTEGER REFERENCES sql_queries(id),
                    csv_separator     VARCHAR(5)  NOT NULL DEFAULT ';',
                    csv_encoding      VARCHAR(20) NOT NULL DEFAULT 'utf-8',
                    csv_chunk_size    INTEGER     NOT NULL DEFAULT 50000,
                    csv_quoting       VARCHAR(20) NOT NULL DEFAULT 'QUOTE_NONNUMERIC',
                    ftp_profile_id    INTEGER REFERENCES ftp_profiles(id),
                    remote_path_tpl   VARCHAR(500),
                    filename_tpl      VARCHAR(255),
                    frequency         VARCHAR(20) NOT NULL DEFAULT 'DAILY',
                    cron_expression   VARCHAR(100),
                    scheduled_time    VARCHAR(10),
                    scheduled_day     INTEGER,
                    is_active         BOOLEAN     NOT NULL DEFAULT 1,
                    prevent_overlap   BOOLEAN     NOT NULL DEFAULT 0,
                    last_status       VARCHAR(20) DEFAULT 'IDLE',
                    last_run_at       DATETIME,
                    next_run_at       DATETIME,
                    created_at        DATETIME,
                    updated_at        DATETIME
                )
            """))
            conn.execute(text("INSERT INTO pipelines_new SELECT * FROM pipelines"))
            conn.execute(text("DROP TABLE pipelines"))
            conn.execute(text("ALTER TABLE pipelines_new RENAME TO pipelines"))
            conn.execute(text("PRAGMA foreign_keys = ON"))
            conn.commit()

        # Chiffrement one-shot des mots de passe encore en clair (bases antérieures au
        # chiffrement au repos). Idempotent : is_encrypted() détecte les lignes déjà
        # migrées et les laisse intactes.
        for table in ("oracle_profiles", "ftp_profiles", "smtp_profiles", "database_profiles"):
            rows = conn.execute(text(
                f"SELECT id, password FROM {table} WHERE password IS NOT NULL AND password != ''"
            )).fetchall()
            for row_id, pwd in rows:
                if not crypto.is_encrypted(pwd):
                    conn.execute(
                        text(f"UPDATE {table} SET password = :pwd WHERE id = :id"),
                        {"pwd": crypto.encrypt(pwd), "id": row_id},
                    )
            if rows:
                conn.commit()

        # Identité stable (UUID) — prérequis à l'export/import (chantier 5). Chacune des
        # trois étapes (colonne / backfill / index) est indépendamment idempotente.
        for table in ("oracle_profiles", "ftp_profiles", "smtp_profiles",
                      "database_profiles", "sql_queries", "pipelines",
                      "ssh_profiles", "kerberos_profiles"):
            cols = {r[1] for r in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()}
            if "uuid" not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN uuid VARCHAR(36)"))
                conn.commit()

            rows = conn.execute(text(f"SELECT id FROM {table} WHERE uuid IS NULL")).fetchall()
            for (row_id,) in rows:
                conn.execute(
                    text(f"UPDATE {table} SET uuid = :u WHERE id = :id"),
                    {"u": str(uuid.uuid4()), "id": row_id},
                )
            if rows:
                conn.commit()

            conn.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS ix_{table}_uuid ON {table}(uuid)"))
            conn.commit()

        # Bilan de santé des connexions (chantier UX fiabilité) — mémorise le résultat du
        # dernier test entre deux sessions, sur les 4 tables de profils.
        for table in ("oracle_profiles", "ftp_profiles", "smtp_profiles", "database_profiles",
                      "ssh_profiles", "kerberos_profiles"):
            profile_cols = {r[1] for r in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()}
            if "last_tested_at" not in profile_cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN last_tested_at DATETIME"))
                conn.commit()
            if "last_test_success" not in profile_cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN last_test_success BOOLEAN"))
                conn.commit()

        # Heure/jour du digest configurables (auparavant fixés en dur à 07:00 / lundi dans
        # core/scheduler.py::refresh_digest_job()).
        notif_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(notification_settings)")).fetchall()}
        if "digest_time" not in notif_cols:
            conn.execute(text(
                "ALTER TABLE notification_settings ADD COLUMN digest_time VARCHAR(5) NOT NULL DEFAULT '07:00'"
            ))
            conn.commit()
        if "digest_day_of_week" not in notif_cols:
            conn.execute(text(
                "ALTER TABLE notification_settings ADD COLUMN digest_day_of_week INTEGER NOT NULL DEFAULT 0"
            ))
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
    _migrate_oracle_steps_to_generic()


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
                           auth_mode="DEFAULT", uuid=None) -> OracleProfile:
    with get_session() as s:
        kwargs = dict(
            name=name, host=host, port=port,
            username=username, password=crypto.encrypt(password),
            service_name=service_name, sid=sid,
            auth_mode=auth_mode,
        )
        if uuid:
            kwargs["uuid"] = uuid
        profile = OracleProfile(**kwargs)
        s.add(profile)
    return profile


def update_oracle_profile(profile_id, name, host, port, username, password=None,
                           service_name=None, sid=None,
                           auth_mode="DEFAULT") -> OracleProfile | None:
    """password=None (ou vide) conserve le mot de passe existant sans le toucher."""
    with get_session() as s:
        p = s.get(OracleProfile, profile_id)
        if not p:
            return None
        p.name = name; p.host = host; p.port = port
        p.username = username
        if password:
            p.password = crypto.encrypt(password)
        p.service_name = service_name
        p.sid = sid
        p.auth_mode = auth_mode
    return p


def get_oracle_profiles() -> list[OracleProfile]:
    with get_session() as s:
        return s.query(OracleProfile).order_by(OracleProfile.name).all()


def get_oracle_profile(profile_id: int) -> OracleProfile | None:
    with get_session() as s:
        return s.get(OracleProfile, profile_id)


def get_oracle_profile_by_uuid(uuid: str) -> OracleProfile | None:
    with get_session() as s:
        return s.query(OracleProfile).filter_by(uuid=uuid).first()


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

def create_ftp_profile(name, host, port, username, password, protocol="FTP", uuid=None) -> FtpProfile:
    with get_session() as s:
        kwargs = dict(
            name=name, host=host, port=port,
            username=username, password=crypto.encrypt(password),
            protocol=protocol,
        )
        if uuid:
            kwargs["uuid"] = uuid
        profile = FtpProfile(**kwargs)
        s.add(profile)
    return profile


def update_ftp_profile(profile_id, name, host, port, username, password=None,
                        protocol="FTP") -> FtpProfile | None:
    """password=None (ou vide) conserve le mot de passe existant sans le toucher."""
    with get_session() as s:
        p = s.get(FtpProfile, profile_id)
        if not p:
            return None
        p.name = name; p.host = host; p.port = port
        p.username = username
        if password:
            p.password = crypto.encrypt(password)
        p.protocol = protocol
    return p


def get_ftp_profiles() -> list[FtpProfile]:
    with get_session() as s:
        return s.query(FtpProfile).order_by(FtpProfile.name).all()


def get_ftp_profile(profile_id: int) -> FtpProfile | None:
    with get_session() as s:
        return s.get(FtpProfile, profile_id)


def get_ftp_profile_by_uuid(uuid: str) -> FtpProfile | None:
    with get_session() as s:
        return s.query(FtpProfile).filter_by(uuid=uuid).first()


def delete_ftp_profile(profile_id: int) -> bool:
    with get_session() as s:
        obj = s.get(FtpProfile, profile_id)
        if obj:
            s.delete(obj)
            return True
    return False


# ──────────────────────────────────────────────
#  HELPERS PROFIL SSH (edge/master node) — étape SPARK_SQL
# ──────────────────────────────────────────────

def create_ssh_profile(name, host, port, username, password, uuid=None) -> SshProfile:
    with get_session() as s:
        kwargs = dict(name=name, host=host, port=port, username=username,
                      password=crypto.encrypt(password))
        if uuid:
            kwargs["uuid"] = uuid
        profile = SshProfile(**kwargs)
        s.add(profile)
    return profile


def update_ssh_profile(profile_id, name, host, port, username, password=None) -> SshProfile | None:
    """password=None (ou vide) conserve le mot de passe existant sans le toucher."""
    with get_session() as s:
        p = s.get(SshProfile, profile_id)
        if not p:
            return None
        p.name = name; p.host = host; p.port = port
        p.username = username
        if password:
            p.password = crypto.encrypt(password)
    return p


def get_ssh_profiles() -> list[SshProfile]:
    with get_session() as s:
        return s.query(SshProfile).order_by(SshProfile.name).all()


def get_ssh_profile(profile_id: int) -> SshProfile | None:
    with get_session() as s:
        return s.get(SshProfile, profile_id)


def get_ssh_profile_by_uuid(uuid: str) -> SshProfile | None:
    with get_session() as s:
        return s.query(SshProfile).filter_by(uuid=uuid).first()


def delete_ssh_profile(profile_id: int) -> bool:
    with get_session() as s:
        obj = s.get(SshProfile, profile_id)
        if obj:
            s.delete(obj)
            return True
    return False


# ──────────────────────────────────────────────
#  HELPERS PROFIL KERBEROS — étape SPARK_SQL
# ──────────────────────────────────────────────

def create_kerberos_profile(name, principal, password, uuid=None) -> KerberosProfile:
    with get_session() as s:
        kwargs = dict(name=name, principal=principal, password=crypto.encrypt(password))
        if uuid:
            kwargs["uuid"] = uuid
        profile = KerberosProfile(**kwargs)
        s.add(profile)
    return profile


def update_kerberos_profile(profile_id, name, principal, password=None) -> KerberosProfile | None:
    """password=None (ou vide) conserve le mot de passe existant sans le toucher."""
    with get_session() as s:
        p = s.get(KerberosProfile, profile_id)
        if not p:
            return None
        p.name = name; p.principal = principal
        if password:
            p.password = crypto.encrypt(password)
    return p


def get_kerberos_profiles() -> list[KerberosProfile]:
    with get_session() as s:
        return s.query(KerberosProfile).order_by(KerberosProfile.name).all()


def get_kerberos_profile(profile_id: int) -> KerberosProfile | None:
    with get_session() as s:
        return s.get(KerberosProfile, profile_id)


def get_kerberos_profile_by_uuid(uuid: str) -> KerberosProfile | None:
    with get_session() as s:
        return s.query(KerberosProfile).filter_by(uuid=uuid).first()


def delete_kerberos_profile(profile_id: int) -> bool:
    with get_session() as s:
        obj = s.get(KerberosProfile, profile_id)
        if obj:
            s.delete(obj)
            return True
    return False


# ──────────────────────────────────────────────
#  HELPERS SMTP PROFILE
# ──────────────────────────────────────────────

def create_smtp_profile(name, host, port, from_address,
                         username=None, password=None, use_tls=True, uuid=None) -> SmtpProfile:
    with get_session() as s:
        kwargs = dict(
            name=name, host=host, port=port,
            username=username, password=crypto.encrypt(password) if password else password,
            use_tls=use_tls, from_address=from_address,
        )
        if uuid:
            kwargs["uuid"] = uuid
        profile = SmtpProfile(**kwargs)
        s.add(profile)
    return profile


def update_smtp_profile(profile_id, name, host, port, from_address,
                         username=None, password=None, use_tls=True) -> SmtpProfile | None:
    """password=None (ou vide) conserve le mot de passe existant sans le toucher."""
    with get_session() as s:
        p = s.get(SmtpProfile, profile_id)
        if not p:
            return None
        p.name = name; p.host = host; p.port = port
        p.username = username
        if password:
            p.password = crypto.encrypt(password)
        p.use_tls = use_tls
        p.from_address = from_address
    return p


def get_smtp_profiles() -> list[SmtpProfile]:
    with get_session() as s:
        return s.query(SmtpProfile).order_by(SmtpProfile.name).all()


def get_smtp_profile(profile_id: int) -> SmtpProfile | None:
    with get_session() as s:
        return s.get(SmtpProfile, profile_id)


def get_smtp_profile_by_uuid(uuid: str) -> SmtpProfile | None:
    with get_session() as s:
        return s.query(SmtpProfile).filter_by(uuid=uuid).first()


def delete_smtp_profile(profile_id: int) -> bool:
    with get_session() as s:
        obj = s.get(SmtpProfile, profile_id)
        if obj:
            s.delete(obj)
            return True
    return False


# ──────────────────────────────────────────────
#  HELPERS PROFIL BASE DE DONNÉES (MySQL / PostgreSQL / SQL Server)
# ──────────────────────────────────────────────

def create_database_profile(name, db_type, host, port, username, password,
                             database_name=None, extra=None, uuid=None) -> DatabaseProfile:
    import json
    with get_session() as s:
        kwargs = dict(
            name=name, db_type=db_type, host=host, port=port,
            username=username, password=crypto.encrypt(password),
            database_name=database_name,
            extra_json=json.dumps(extra or {}),
        )
        if uuid:
            kwargs["uuid"] = uuid
        profile = DatabaseProfile(**kwargs)
        s.add(profile)
    return profile


def update_database_profile(profile_id, name, db_type, host, port, username, password=None,
                             database_name=None, extra=None) -> DatabaseProfile | None:
    """password=None (ou vide) conserve le mot de passe existant sans le toucher."""
    import json
    with get_session() as s:
        p = s.get(DatabaseProfile, profile_id)
        if not p:
            return None
        p.name = name; p.db_type = db_type; p.host = host; p.port = port
        p.username = username
        if password:
            p.password = crypto.encrypt(password)
        p.database_name = database_name
        p.extra_json = json.dumps(extra or {})
    return p


def get_database_profiles() -> list[DatabaseProfile]:
    with get_session() as s:
        return s.query(DatabaseProfile).order_by(DatabaseProfile.name).all()


def get_database_profile(profile_id: int) -> DatabaseProfile | None:
    with get_session() as s:
        return s.get(DatabaseProfile, profile_id)


def get_database_profile_by_uuid(uuid: str) -> DatabaseProfile | None:
    with get_session() as s:
        return s.query(DatabaseProfile).filter_by(uuid=uuid).first()


def delete_database_profile(profile_id: int) -> bool:
    with get_session() as s:
        obj = s.get(DatabaseProfile, profile_id)
        if obj:
            s.delete(obj)
            return True
    return False


def list_all_db_profiles() -> list[dict]:
    """
    Fusionne OracleProfile et DatabaseProfile en une liste unique et légère —
    pour l'affichage unifié (page Connexions) et les sélecteurs de profil des steps
    DB_EXTRACT/DB_EXECUTE/DB_LOAD, qui doivent pouvoir référencer n'importe quel moteur.
    """
    with get_session() as s:
        rows = []
        for p in s.query(OracleProfile).order_by(OracleProfile.name).all():
            rows.append({
                "db_type": "ORACLE", "id": p.id, "name": p.name,
                "host": p.host, "port": p.port, "username": p.username,
                "last_test_success": p.last_test_success,
            })
        for p in s.query(DatabaseProfile).order_by(DatabaseProfile.name).all():
            rows.append({
                "db_type": _status_str(p.db_type), "id": p.id, "name": p.name,
                "host": p.host, "port": p.port, "username": p.username,
                "last_test_success": p.last_test_success,
            })
        rows.sort(key=lambda r: r["name"])
        return rows


def _status_str(val) -> str:
    return val.value if hasattr(val, "value") else str(val or "")


# ──────────────────────────────────────────────
#  HELPERS SQL QUERY
# ──────────────────────────────────────────────

def create_sql_query(name, sql_text, description=None, oracle_profile_id=None, uuid=None) -> SqlQuery:
    with get_session() as s:
        kwargs = dict(
            name=name, sql_text=sql_text,
            description=description,
            oracle_profile_id=oracle_profile_id,
        )
        if uuid:
            kwargs["uuid"] = uuid
        q = SqlQuery(**kwargs)
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


def get_sql_query_by_uuid(uuid: str) -> SqlQuery | None:
    with get_session() as s:
        return s.query(SqlQuery).filter_by(uuid=uuid).first()


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
                    prevent_overlap=False,
                    # Champs legacy conservés pour compatibilité migration
                    oracle_profile_id=None, sql_query_id=None, ftp_profile_id=None,
                    remote_path_tpl=None, filename_tpl=None,
                    csv_separator=";", csv_encoding="utf-8", csv_chunk_size=50000,
                    csv_quoting="QUOTE_NONNUMERIC", uuid=None) -> Pipeline:
    with get_session() as s:
        kwargs = dict(
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
            prevent_overlap=prevent_overlap,
        )
        if uuid:
            kwargs["uuid"] = uuid
        p = Pipeline(**kwargs)
        s.add(p)
    log_audit_event("pipeline_created", pipeline_id=p.id, pipeline_name=p.name)
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


def get_pipeline_by_uuid(uuid: str) -> Pipeline | None:
    with get_session() as s:
        return s.query(Pipeline).filter_by(uuid=uuid).first()


def update_pipeline(pipeline_id, name, description=None,
                     frequency="DAILY", cron_expression=None,
                     scheduled_time="06:00", scheduled_day=None,
                     prevent_overlap=False) -> Pipeline | None:
    """Ne touche pas aux étapes — voir save_steps() pour ça (chantier 5c : écrasement à l'import)."""
    with get_session() as s:
        p = s.get(Pipeline, pipeline_id)
        if not p:
            return None
        p.name = name
        p.description = description
        p.frequency = frequency
        p.cron_expression = cron_expression
        p.scheduled_time = scheduled_time
        p.scheduled_day = scheduled_day
        p.prevent_overlap = prevent_overlap
    log_audit_event("pipeline_edited", pipeline_id=pipeline_id, pipeline_name=name,
                     detail="Nom/description/planification")
    return p


def set_pipeline_active(pipeline_id: int, active: bool) -> bool:
    with get_session() as s:
        obj = s.get(Pipeline, pipeline_id)
        if obj:
            obj.is_active = active
            return True
    return False


def delete_pipeline(pipeline_id: int) -> bool:
    name = None
    with get_session() as s:
        obj = s.get(Pipeline, pipeline_id)
        if not obj:
            return False
        name = obj.name
        s.delete(obj)
    log_audit_event("pipeline_deleted", pipeline_id=pipeline_id, pipeline_name=name)
    return True


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


def get_run_counts_by_day(days: int = 30, pipeline_id: int | None = None) -> list[dict]:
    """
    Agrégat pour le graphique d'activité du Dashboard (chantier UX statistiques) : nombre de
    runs par jour et par statut sur les `days` derniers jours (aujourd'hui inclus). Zéro-rempli
    pour les jours sans exécution — continuité indispensable pour un graphique de tendance, un
    jour manquant doit apparaître à zéro plutôt que disparaître du graphe. Chaque entrée :
    {"date": date, "success": int, "failed": int, "cancelled": int}, la plus ancienne en premier.

    `pipeline_id` optionnel (défaut None, comportement global inchangé) filtre sur un seul
    pipeline — réutilisé tel quel par la vue détail par pipeline (chantier UX fiabilité, D.1).
    """
    from datetime import date, datetime, timedelta

    from sqlalchemy import func

    today      = date.today()
    start_date = today - timedelta(days=days - 1)
    start_dt   = datetime.combine(start_date, datetime.min.time())

    with get_session() as s:
        q = s.query(
            func.strftime("%Y-%m-%d", PipelineRun.started_at).label("day"),
            PipelineRun.status,
            func.count(PipelineRun.id),
        ).filter(PipelineRun.started_at >= start_dt)
        if pipeline_id is not None:
            q = q.filter(PipelineRun.pipeline_id == pipeline_id)
        rows = q.group_by("day", PipelineRun.status).all()

    counts: dict[str, dict[str, int]] = {}
    for day_str, status, n in rows:
        status_str = status.value if hasattr(status, "value") else str(status)
        counts.setdefault(day_str, {})[status_str] = n

    result = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        day_counts = counts.get(d.isoformat(), {})
        result.append({
            "date":      d,
            "success":   day_counts.get("SUCCESS", 0),
            "failed":    day_counts.get("FAILED", 0),
            "cancelled": day_counts.get("CANCELLED", 0),
        })
    return result


# ──────────────────────────────────────────────
#  PARAMÈTRES DE NOTIFICATION (digest manager)
# ──────────────────────────────────────────────

def get_notification_settings() -> NotificationSettings:
    """Get-or-create la ligne singleton (id=1) — jamais absente après le premier appel."""
    with get_session() as s:
        settings = s.get(NotificationSettings, 1)
        if not settings:
            settings = NotificationSettings(id=1)
            s.add(settings)
    return settings


def update_notification_settings(**kwargs) -> NotificationSettings:
    """Met à jour un sous-ensemble de champs de la ligne singleton (get-or-create implicite)."""
    with get_session() as s:
        settings = s.get(NotificationSettings, 1)
        if not settings:
            settings = NotificationSettings(id=1)
            s.add(settings)
        for key, value in kwargs.items():
            setattr(settings, key, value)
    return settings


# ──────────────────────────────────────────────
#  BILAN DE SANTÉ DES CONNEXIONS (chantier UX fiabilité)
# ──────────────────────────────────────────────

_PROFILE_MODEL_BY_CATEGORY = {
    "oracle":   OracleProfile,
    "ftp":      FtpProfile,
    "smtp":     SmtpProfile,
    "database": DatabaseProfile,
    "ssh":      SshProfile,
    "kerberos": KerberosProfile,
}


def record_profile_test_result(category: str, profile_id: int, success: bool) -> None:
    """
    Mémorise le résultat d'un test de connexion pour un profil déjà enregistré — appelé aussi
    bien par les 4 dialogues de profil (bouton "Tester" existant) que par le bilan de santé
    groupé, pour que chaque test déjà effectué alimente le tableau gratuitement.
    """
    from datetime import datetime
    model = _PROFILE_MODEL_BY_CATEGORY.get(category)
    if model is None:
        return
    with get_session() as s:
        obj = s.get(model, profile_id)
        if obj:
            obj.last_tested_at = datetime.utcnow()
            obj.last_test_success = success


# ──────────────────────────────────────────────
#  JOURNAL D'AUDIT
# ──────────────────────────────────────────────

def log_audit_event(event_type: str, pipeline_id: int | None = None,
                     pipeline_name: str | None = None, detail: str | None = None) -> AuditEvent:
    """
    Insère une ligne d'audit — appelé aux points d'écriture existants (create_pipeline,
    update_pipeline, save_steps, save_pipeline_graph, delete_pipeline, export_pipeline_to_file,
    apply_import), jamais de nouvelle logique métier. `actor` capturé ici, pas par l'appelant :
    un seul endroit à connaître getpass.getuser().
    """
    import getpass
    try:
        actor = getpass.getuser()
    except Exception:
        actor = None

    with get_session() as s:
        event = AuditEvent(
            event_type=event_type, pipeline_id=pipeline_id,
            pipeline_name=pipeline_name, actor=actor, detail=detail,
        )
        s.add(event)
    return event


def get_audit_events(limit: int = 200, pipeline_id: int | None = None) -> list[AuditEvent]:
    with get_session() as s:
        q = s.query(AuditEvent)
        if pipeline_id is not None:
            q = q.filter(AuditEvent.pipeline_id == pipeline_id)
        return q.order_by(AuditEvent.timestamp.desc()).limit(limit).all()


# ──────────────────────────────────────────────
#  HELPERS PIPELINE STEPS
# ──────────────────────────────────────────────

def get_steps(pipeline_id: int) -> list[PipelineStep]:
    with get_session() as s:
        return (s.query(PipelineStep)
                  .filter_by(pipeline_id=pipeline_id)
                  .order_by(PipelineStep.step_order)
                  .all())


def find_pipelines_using_profile(config_key: str, profile_id: int) -> list[str]:
    """
    Cherche les pipelines dont une étape référence `profile_id` sous la clé
    `config_key` (ex: "oracle_profile_id", "ftp_profile_id", "smtp_profile_id")
    dans son config_json. La référence n'étant pas une vraie contrainte de clé
    étrangère (elle vit dans un blob JSON), c'est le seul moyen de la détecter
    avant de supprimer un profil — évite de casser silencieusement un pipeline.

    Retourne les noms de pipelines concernés (dédupliqués, triés).
    """
    import json
    with get_session() as s:
        steps = s.query(PipelineStep).options(joinedload(PipelineStep.pipeline)).all()
        names = set()
        for step in steps:
            try:
                config = json.loads(step.config_json or "{}")
            except ValueError:
                continue
            if config.get(config_key) == profile_id and step.pipeline:
                names.add(step.pipeline.name)
        return sorted(names)


def find_pipelines_using_db_profile(db_type: str, profile_id: int) -> list[str]:
    """
    Comme find_pipelines_using_profile, mais pour les steps génériques DB_EXTRACT/
    DB_EXECUTE/DB_LOAD : leur config porte à la fois "profile_id" et "db_type" — il faut
    vérifier les deux, sinon un profil Oracle et un profil MySQL qui partagent le même id
    numérique produiraient un faux positif (ou négatif) l'un pour l'autre.
    """
    import json
    with get_session() as s:
        steps = s.query(PipelineStep).options(joinedload(PipelineStep.pipeline)).all()
        names = set()
        for step in steps:
            try:
                config = json.loads(step.config_json or "{}")
            except ValueError:
                continue
            if (config.get("profile_id") == profile_id
                    and config.get("db_type") == db_type
                    and step.pipeline):
                names.add(step.pipeline.name)
        return sorted(names)


def save_steps(pipeline_id: int, steps: list[dict]) -> None:
    """Remplace toutes les étapes d'un pipeline.

    Chaque dict : {"step_type": str, "label": str|None, "config": dict,
                    "retry_count": int|None, "run_always": bool|None}
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
                retry_count=step.get("retry_count") or 0,
                run_always=step.get("run_always") or False,
            ))
    pipeline = get_pipeline(pipeline_id)
    log_audit_event(
        "pipeline_edited", pipeline_id=pipeline_id,
        pipeline_name=pipeline.name if pipeline else None,
        detail=f"{len(steps)} étape(s) (éditeur linéaire)",
    )


# ──────────────────────────────────────────────
#  GRAPHE DE PIPELINE (chantier 6a) — arêtes + positions
# ──────────────────────────────────────────────

def get_edges(pipeline_id: int) -> list[PipelineEdge]:
    with get_session() as s:
        return s.query(PipelineEdge).filter_by(pipeline_id=pipeline_id).all()


def save_pipeline_graph(pipeline_id: int, steps: list[dict], edges: list[dict]) -> None:
    """
    Comme save_steps(), mais persiste aussi la position sur le canevas (pos_x/pos_y, 0 par
    défaut si absente du dict) et remplace intégralement les PipelineEdge du pipeline.

    N'est appelée que par le futur éditeur graphique (chantier 6b) — save_steps() reste le
    chemin de l'éditeur linéaire existant (PipelineEditorDialog), inchangé.

    Chaque edge dict : {"from_step_key": str, "from_port": str, "to_step_key": str, "to_port": str}.
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
                retry_count=step.get("retry_count") or 0,
                run_always=step.get("run_always") or False,
                pos_x=step.get("pos_x", 0),
                pos_y=step.get("pos_y", 0),
            ))
        s.query(PipelineEdge).filter_by(pipeline_id=pipeline_id).delete()
        for e in edges:
            s.add(PipelineEdge(
                pipeline_id=pipeline_id,
                from_step_key=e["from_step_key"],
                from_port=e.get("from_port") or "output_file",
                to_step_key=e["to_step_key"],
                to_port=e.get("to_port") or "input",
            ))
    pipeline = get_pipeline(pipeline_id)
    log_audit_event(
        "pipeline_edited", pipeline_id=pipeline_id,
        pipeline_name=pipeline.name if pipeline else None,
        detail=f"{len(steps)} étape(s), {len(edges)} arête(s) (éditeur graphique)",
    )


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
                step_type=StepType.DB_EXTRACT,
                label="Extraction Oracle",
                config_json=json.dumps({
                    "db_type":           "ORACLE",
                    "profile_id":        p.oracle_profile_id,
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


# ──────────────────────────────────────────────
#  MIGRATION ORACLE_* → DB_* (steps génériques multi-moteurs)
# ──────────────────────────────────────────────

def _migrate_oracle_steps_to_generic() -> None:
    """
    Réécrit les PipelineStep encore sur les anciens types Oracle-spécifiques
    (ORACLE_EXTRACT/ORACLE_EXECUTE/ORACLE_LOAD, dépréciés) vers les types génériques
    équivalents (DB_EXTRACT/DB_EXECUTE/DB_LOAD), en ajoutant "db_type": "ORACLE" et en
    renommant la clé "oracle_profile_id" en "profile_id" dans leur config_json.
    Idempotent — ne touche que les steps encore sur l'ancien type.
    """
    import json
    if _SessionFactory is None:
        return

    mapping = {
        StepType.ORACLE_EXTRACT: StepType.DB_EXTRACT,
        StepType.ORACLE_EXECUTE: StepType.DB_EXECUTE,
        StepType.ORACLE_LOAD:    StepType.DB_LOAD,
    }
    with get_session() as s:
        steps = (s.query(PipelineStep)
                   .filter(PipelineStep.step_type.in_(list(mapping.keys())))
                   .all())
        for step in steps:
            new_type = mapping[step.step_type]
            config = json.loads(step.config_json or "{}")
            if "oracle_profile_id" in config:
                config["profile_id"] = config.pop("oracle_profile_id")
            config["db_type"] = "ORACLE"
            step.step_type = new_type
            step.config_json = json.dumps(config)