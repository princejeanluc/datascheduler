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
import uuid as _uuid_module

Base = declarative_base()


def _new_uuid() -> str:
    """Identifiant stable, indépendant du nom (mutable) — prérequis à l'export/import."""
    return str(_uuid_module.uuid4())


# ──────────────────────────────────────────────
#  ENUMS
# ──────────────────────────────────────────────

class FtpProtocol(str, enum.Enum):
    FTP  = "FTP"
    FTPS = "FTPS"
    SFTP = "SFTP"


class PipelineStatus(str, enum.Enum):
    IDLE      = "IDLE"
    RUNNING   = "RUNNING"
    SUCCESS   = "SUCCESS"
    FAILED    = "FAILED"
    CANCELLED = "CANCELLED"


class CronFrequency(str, enum.Enum):
    DAILY   = "DAILY"
    WEEKLY  = "WEEKLY"
    MONTHLY = "MONTHLY"
    CUSTOM  = "CUSTOM"   # syntaxe cron brute


class DbType(str, enum.Enum):
    ORACLE     = "ORACLE"
    MYSQL      = "MYSQL"
    POSTGRESQL = "POSTGRESQL"
    SQLSERVER  = "SQLSERVER"


class StepType(str, enum.Enum):
    # Dépréciés — remplacés par DB_EXTRACT/DB_EXECUTE/DB_LOAD (génériques, tout moteur).
    # Conservés uniquement pour que SQLAlchemy ne plante pas si une ligne pipeline_steps
    # non migrée traîne encore ; ils ne sont plus enregistrés dans le registre ni l'UI.
    ORACLE_EXTRACT = "ORACLE_EXTRACT"
    ORACLE_EXECUTE = "ORACLE_EXECUTE"
    ORACLE_LOAD    = "ORACLE_LOAD"

    FTP_UPLOAD     = "FTP_UPLOAD"      # Upload vers serveur FTP/SFTP
    LOCAL_COPY     = "LOCAL_COPY"      # Copie locale avec tokens datetime
    PYTHON_SCRIPT  = "PYTHON_SCRIPT"   # Exécution d'un script .py
    FTP_DOWNLOAD   = "FTP_DOWNLOAD"    # Téléchargement FTP/FTPS/SFTP (source de pipeline)
    EMAIL_NOTIFY   = "EMAIL_NOTIFY"    # Envoi d'un email (avec pièce jointe optionnelle)
    HTTP_REQUEST   = "HTTP_REQUEST"    # Appel HTTP (API REST / webhook)
    DB_EXTRACT     = "DB_EXTRACT"      # Base de données (tout moteur) → CSV temporaire
    DB_EXECUTE     = "DB_EXECUTE"      # Exécution SQL/PLSQL sans extraction (tout moteur)
    DB_LOAD        = "DB_LOAD"         # Chargement d'un CSV vers une table (tout moteur)
    CONDITION      = "CONDITION"       # Routeur conditionnel (ports de sortie nommés) — chantier 6a


# ──────────────────────────────────────────────
#  PROFIL ORACLE
# ──────────────────────────────────────────────

class OracleProfile(Base):
    __tablename__ = "oracle_profiles"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    uuid         = Column(String(36), unique=True, nullable=False, default=_new_uuid)
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
    uuid       = Column(String(36), unique=True, nullable=False, default=_new_uuid)
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
#  PROFIL SMTP
# ──────────────────────────────────────────────

class SmtpProfile(Base):
    __tablename__ = "smtp_profiles"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    uuid         = Column(String(36), unique=True, nullable=False, default=_new_uuid)
    name         = Column(String(100), unique=True, nullable=False)
    host         = Column(String(255), nullable=False)
    port         = Column(Integer, default=587, nullable=False)
    username     = Column(String(100), nullable=True)
    password     = Column(String(255), nullable=True)  # chiffré en prod (étape 2)
    use_tls      = Column(Boolean, default=True, nullable=False)
    from_address = Column(String(255), nullable=False)
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<SmtpProfile name={self.name} host={self.host}:{self.port}>"


# ──────────────────────────────────────────────
#  PROFIL BASE DE DONNÉES GÉNÉRIQUE (MySQL / PostgreSQL / SQL Server)
# ──────────────────────────────────────────────

class DatabaseProfile(Base):
    """
    Profil de connexion pour les moteurs non-Oracle (structure identique entre eux :
    host/port/user/password/nom de base). Oracle garde sa propre table (OracleProfile) —
    ses champs service_name/sid/auth_mode sont trop spécifiques pour être généralisés ici.
    """
    __tablename__ = "database_profiles"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    uuid          = Column(String(36), unique=True, nullable=False, default=_new_uuid)
    name          = Column(String(100), unique=True, nullable=False)
    db_type       = Column(Enum(DbType), nullable=False)
    host          = Column(String(255), nullable=False)
    port          = Column(Integer, nullable=False)
    username      = Column(String(100), nullable=False)
    password      = Column(String(255), nullable=False)  # chiffré en prod (étape 2)
    database_name = Column(String(100), nullable=True)
    extra_json    = Column(Text, nullable=False, default="{}")  # options propres au moteur
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<DatabaseProfile name={self.name} db_type={self.db_type} host={self.host}:{self.port}>"


# ──────────────────────────────────────────────
#  REQUÊTE SQL RÉUTILISABLE
# ──────────────────────────────────────────────

class SqlQuery(Base):
    __tablename__ = "sql_queries"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    uuid              = Column(String(36), unique=True, nullable=False, default=_new_uuid)
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
    uuid              = Column(String(36), unique=True, nullable=False, default=_new_uuid)
    name              = Column(String(100), unique=True, nullable=False)
    description       = Column(Text, nullable=True)

    # Source (nullable — défini via les étapes du pipeline)
    oracle_profile_id = Column(Integer, ForeignKey("oracle_profiles.id"), nullable=True)
    sql_query_id      = Column(Integer, ForeignKey("sql_queries.id"),     nullable=True)

    # Export CSV
    csv_separator     = Column(String(5),   default=";",                 nullable=False)
    csv_encoding      = Column(String(20),  default="utf-8",             nullable=False)
    csv_chunk_size    = Column(Integer,     default=50000,               nullable=False)
    csv_quoting       = Column(String(20),  default="QUOTE_NONNUMERIC",  nullable=False)

    # Destination FTP (nullable — défini via les étapes du pipeline)
    ftp_profile_id    = Column(Integer, ForeignKey("ftp_profiles.id"), nullable=True)
    remote_path_tpl   = Column(String(500), nullable=True)
    filename_tpl      = Column(String(255), nullable=True)

    # Planification
    frequency         = Column(Enum(CronFrequency), default=CronFrequency.DAILY, nullable=False)
    cron_expression   = Column(String(100), nullable=True)    # utilisé si CUSTOM ou calculé sinon
    scheduled_time    = Column(String(10),  nullable=True)    # HH:MM pour DAILY/WEEKLY/MONTHLY
    scheduled_day     = Column(Integer,     nullable=True)    # 0=lundi … 6=dimanche (WEEKLY) / 1-31 (MONTHLY)

    # État
    is_active         = Column(Boolean, default=True, nullable=False)
    prevent_overlap   = Column(Boolean, default=False, nullable=False)
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
    steps          = relationship("PipelineStep",  back_populates="pipeline",
                                  cascade="all, delete-orphan",
                                  order_by="PipelineStep.step_order")
    edges          = relationship("PipelineEdge",  back_populates="pipeline",
                                  cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Pipeline name={self.name} active={self.is_active}>"


# ──────────────────────────────────────────────
#  ÉTAPE DE PIPELINE
# ──────────────────────────────────────────────

class PipelineStep(Base):
    __tablename__ = "pipeline_steps"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    pipeline_id = Column(Integer, ForeignKey("pipelines.id"), nullable=False)
    step_order  = Column(Integer, nullable=False, default=0)
    step_type   = Column(Enum(StepType), nullable=False)
    label       = Column(String(100), nullable=True)   # libellé optionnel
    config_json = Column(Text, nullable=False, default="{}")
    retry_count = Column(Integer, default=0, nullable=False)
    run_always  = Column(Boolean, default=False, nullable=False)
    pos_x       = Column(Integer, nullable=False, default=0)   # position canevas — chantier 6a/6b
    pos_y       = Column(Integer, nullable=False, default=0)

    pipeline = relationship("Pipeline", back_populates="steps")

    def __repr__(self):
        return f"<PipelineStep pipeline_id={self.pipeline_id} order={self.step_order} type={self.step_type}>"


# ──────────────────────────────────────────────
#  ARÊTE DE GRAPHE (chantier 6a)
# ──────────────────────────────────────────────

class PipelineEdge(Base):
    """
    Connexion entre le port de sortie d'une étape et le port d'entrée d'une autre, dans le
    modèle de graphe (chantier 6a/6b). Référence les étapes par leur `_step_key` stable (vivant
    dans PipelineStep.config_json depuis le chantier 3) et non par PipelineStep.id, qui n'est
    pas stable — save_steps()/save_pipeline_graph() suppriment et recréent toutes les lignes à
    chaque sauvegarde. Mécanisme parallèle à `reads_from_step_key` (chantier 3, propre à
    l'éditeur linéaire) — pas un remplacement, les deux coexistent, chacun pour son éditeur.
    """
    __tablename__ = "pipeline_edges"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    pipeline_id   = Column(Integer, ForeignKey("pipelines.id"), nullable=False)
    from_step_key = Column(String(36), nullable=False)
    from_port     = Column(String(50), nullable=False, default="output_file")
    to_step_key   = Column(String(36), nullable=False)
    to_port       = Column(String(50), nullable=False, default="input")

    pipeline = relationship("Pipeline", back_populates="edges")

    def __repr__(self):
        return f"<PipelineEdge {self.from_step_key}:{self.from_port} -> {self.to_step_key}:{self.to_port}>"


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


# ──────────────────────────────────────────────
#  PARAMÈTRES DE NOTIFICATION (digest manager)
# ──────────────────────────────────────────────

class NotificationSettings(Base):
    """
    Ligne singleton (id=1 toujours) — pas de notion multi-utilisateur dans cette app
    mono-poste, un seul jeu de paramètres de digest pour l'installation.
    """
    __tablename__ = "notification_settings"

    id                      = Column(Integer, primary_key=True, default=1)
    digest_enabled          = Column(Boolean, default=False, nullable=False)
    digest_smtp_profile_id  = Column(Integer, ForeignKey("smtp_profiles.id"), nullable=True)
    digest_recipients       = Column(Text, nullable=True)    # adresses séparées par virgule
    digest_frequency        = Column(String(10), default="DAILY", nullable=False)  # DAILY | WEEKLY
    digest_last_sent_at     = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<NotificationSettings enabled={self.digest_enabled} frequency={self.digest_frequency}>"