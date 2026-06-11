"""
DataScheduler — Modèles de données SQLAlchemy (SQLite)
"""

from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Text,
    DateTime, Boolean, ForeignKey, Enum
)
from sqlalchemy.orm import declarative_base, relationship, Session
import enum

Base = declarative_base()


# ──────────────────────────────────────────────
#  ENUMS
# ──────────────────────────────────────────────

class FtpProtocol(str, enum.Enum):
    FTP  = "FTP"
    FTPS = "FTPS"
    SFTP = "SFTP"


class PipelineStatus(str, enum.Enum):
    IDLE    = "IDLE"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED  = "FAILED"


class CronFrequency(str, enum.Enum):
    DAILY   = "DAILY"
    WEEKLY  = "WEEKLY"
    MONTHLY = "MONTHLY"
    CUSTOM  = "CUSTOM"   # syntaxe cron brute


# ──────────────────────────────────────────────
#  PROFIL ORACLE
# ──────────────────────────────────────────────

class OracleProfile(Base):
    __tablename__ = "oracle_profiles"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    name         = Column(String(100), unique=True, nullable=False)
    host         = Column(String(255), nullable=False)
    port         = Column(Integer, default=1521, nullable=False)
    service_name = Column(String(100), nullable=True)   # service name OU sid
    sid          = Column(String(100), nullable=True)
    username     = Column(String(100), nullable=False)
    password     = Column(String(255), nullable=False)  # chiffré en prod (étape 2)
    auth_mode    = Column(String(20),  default="DEFAULT", nullable=False)  # DEFAULT | SYSDBA | SYSOPER
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    queries   = relationship("SqlQuery",  back_populates="oracle_profile")
    pipelines = relationship("Pipeline",  back_populates="oracle_profile")

    def __repr__(self):
        return f"<OracleProfile name={self.name} host={self.host}:{self.port}>"


# ──────────────────────────────────────────────
#  PROFIL FTP
# ──────────────────────────────────────────────

class FtpProfile(Base):
    __tablename__ = "ftp_profiles"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(100), unique=True, nullable=False)
    host       = Column(String(255), nullable=False)
    port       = Column(Integer, default=21, nullable=False)
    username   = Column(String(100), nullable=False)
    password   = Column(String(255), nullable=False)  # chiffré en prod (étape 2)
    protocol   = Column(Enum(FtpProtocol), default=FtpProtocol.FTP, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    pipelines = relationship("Pipeline", back_populates="ftp_profile")

    def __repr__(self):
        return f"<FtpProfile name={self.name} host={self.host} protocol={self.protocol}>"


# ──────────────────────────────────────────────
#  REQUÊTE SQL RÉUTILISABLE
# ──────────────────────────────────────────────

class SqlQuery(Base):
    __tablename__ = "sql_queries"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    name              = Column(String(100), unique=True, nullable=False)
    sql_text          = Column(Text, nullable=False)
    description       = Column(Text, nullable=True)
    oracle_profile_id = Column(Integer, ForeignKey("oracle_profiles.id"), nullable=True)
    created_at        = Column(DateTime, default=datetime.utcnow)
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    oracle_profile = relationship("OracleProfile", back_populates="queries")
    pipelines      = relationship("Pipeline",      back_populates="sql_query")

    def __repr__(self):
        return f"<SqlQuery name={self.name}>"


# ──────────────────────────────────────────────
#  PIPELINE
# ──────────────────────────────────────────────

class Pipeline(Base):
    __tablename__ = "pipelines"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    name              = Column(String(100), unique=True, nullable=False)
    description       = Column(Text, nullable=True)

    # Source
    oracle_profile_id = Column(Integer, ForeignKey("oracle_profiles.id"), nullable=False)
    sql_query_id      = Column(Integer, ForeignKey("sql_queries.id"),     nullable=False)

    # Export CSV
    csv_separator     = Column(String(5),   default=";",                 nullable=False)
    csv_encoding      = Column(String(20),  default="utf-8",             nullable=False)
    csv_chunk_size    = Column(Integer,     default=50000,               nullable=False)
    csv_quoting       = Column(String(20),  default="QUOTE_NONNUMERIC",  nullable=False)

    # Destination FTP
    ftp_profile_id    = Column(Integer, ForeignKey("ftp_profiles.id"), nullable=False)
    remote_path_tpl   = Column(String(500), nullable=False)   # ex: /export/{yyyy}/{MM}/
    filename_tpl      = Column(String(255), nullable=False)   # ex: ventes_{yyyyMMdd}.csv

    # Planification
    frequency         = Column(Enum(CronFrequency), default=CronFrequency.DAILY, nullable=False)
    cron_expression   = Column(String(100), nullable=True)    # utilisé si CUSTOM ou calculé sinon
    scheduled_time    = Column(String(10),  nullable=True)    # HH:MM pour DAILY/WEEKLY/MONTHLY
    scheduled_day     = Column(Integer,     nullable=True)    # 0=lundi … 6=dimanche (WEEKLY) / 1-31 (MONTHLY)

    # État
    is_active         = Column(Boolean, default=True, nullable=False)
    last_status       = Column(Enum(PipelineStatus), default=PipelineStatus.IDLE)
    last_run_at       = Column(DateTime, nullable=True)
    next_run_at       = Column(DateTime, nullable=True)

    created_at        = Column(DateTime, default=datetime.utcnow)
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    oracle_profile = relationship("OracleProfile", back_populates="pipelines")
    ftp_profile    = relationship("FtpProfile",    back_populates="pipelines")
    sql_query      = relationship("SqlQuery",      back_populates="pipelines")
    runs           = relationship("PipelineRun",   back_populates="pipeline",
                                  cascade="all, delete-orphan",
                                  order_by="PipelineRun.started_at.desc()")

    def __repr__(self):
        return f"<Pipeline name={self.name} active={self.is_active}>"


# ──────────────────────────────────────────────
#  HISTORIQUE D'EXÉCUTION
# ──────────────────────────────────────────────

class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    pipeline_id   = Column(Integer, ForeignKey("pipelines.id"), nullable=False)

    started_at    = Column(DateTime, default=datetime.utcnow)
    finished_at   = Column(DateTime, nullable=True)
    status        = Column(Enum(PipelineStatus), default=PipelineStatus.RUNNING)

    rows_exported = Column(Integer,  nullable=True)   # nombre de lignes extraites
    remote_path   = Column(String(500), nullable=True)  # chemin FTP réel du fichier déposé
    error_message = Column(Text,     nullable=True)
    log_text      = Column(Text,     nullable=True)   # log complet de l'exécution

    # Relation
    pipeline = relationship("Pipeline", back_populates="runs")

    @property
    def duration_seconds(self):
        if self.finished_at and self.started_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def __repr__(self):
        return f"<PipelineRun pipeline_id={self.pipeline_id} status={self.status}>"