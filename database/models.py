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


class TriggerCondition(str, enum.Enum):
    """Déclenchement conditionnel d'un pipeline après un autre (chantier P) — SUCCESS/FAILURE ne
    couvrent délibérément pas CANCELLED : un arrêt demandé par l'utilisateur ne doit jamais
    déclencher de cascade automatique, voir core/pipeline.py::_trigger_downstream_pipelines()."""
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    ALWAYS  = "ALWAYS"


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
    SPARK_SQL      = "SPARK_SQL"       # Requête Spark SQL via edge node SSH + Kerberos
    COMPRESS       = "COMPRESS"        # Compression en archive ZIP
    SQOOP_EXPORT   = "SQOOP_EXPORT"    # Export Hive/HCatalog → Oracle via Sqoop, edge node SSH + Kerberos


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
    # Bilan de santé des connexions (chantier UX fiabilité) — mémorisé entre sessions, alimenté
    # par le bouton "Tester" du dialogue de profil ET par le bilan de santé groupé.
    last_tested_at    = Column(DateTime, nullable=True)
    last_test_success = Column(Boolean, nullable=True)

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
    last_tested_at    = Column(DateTime, nullable=True)
    last_test_success = Column(Boolean, nullable=True)

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
    last_tested_at    = Column(DateTime, nullable=True)
    last_test_success = Column(Boolean, nullable=True)

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
    last_tested_at    = Column(DateTime, nullable=True)
    last_test_success = Column(Boolean, nullable=True)

    def __repr__(self):
        return f"<DatabaseProfile name={self.name} db_type={self.db_type} host={self.host}:{self.port}>"


# ──────────────────────────────────────────────
#  PROFIL SSH (edge/master node) — étape SPARK_SQL
# ──────────────────────────────────────────────

class SshProfile(Base):
    """Connexion SSH à un nœud edge/master d'un cluster Hadoop — étape SPARK_SQL."""
    __tablename__ = "ssh_profiles"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    uuid       = Column(String(36), unique=True, nullable=False, default=_new_uuid)
    name       = Column(String(100), unique=True, nullable=False)
    host       = Column(String(255), nullable=False)
    port       = Column(Integer, default=22, nullable=False)
    username   = Column(String(100), nullable=False)
    password   = Column(String(255), nullable=False)  # chiffré
    # Bastion optionnel : si renseigné, ce profil n'est joignable qu'en passant d'abord par
    # jump_via_id (ex: edge03 n'est accessible que depuis edge01) — chantier M. Auto-référence,
    # premier cas de profil pointant vers un autre profil de la même table dans ce schéma.
    # Volontairement pas de relationship() ORM ici : tout le reste du code de ce module accède
    # aux profils via des requêtes explicites (get_session() par appel, jamais d'objet partagé
    # entre sessions) — une relationship self-référentielle se chargerait paresseusement et
    # lèverait DetachedInstanceError dès que l'appelant relit .jump_via après la fermeture de la
    # session qui a chargé le profil (le cas normal : config_from_profile() est appelé bien après
    # get_ssh_profile()). La résolution de la chaîne se fait via de nouveaux appels explicites à
    # get_ssh_profile(profile.jump_via_id), cohérent avec le reste du fichier.
    jump_via_id = Column(Integer, ForeignKey("ssh_profiles.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_tested_at    = Column(DateTime, nullable=True)
    last_test_success = Column(Boolean, nullable=True)

    def __repr__(self):
        return f"<SshProfile name={self.name} host={self.host}:{self.port}>"


# ──────────────────────────────────────────────
#  PROFIL KERBEROS — étape SPARK_SQL
# ──────────────────────────────────────────────

class KerberosProfile(Base):
    """Identité Kerberos (kinit) — nominative, fournie par l'équipe Big Data. Ne peut pas se
    tester seule : requiert un SshProfile pour lancer kinit (voir core/spark.py)."""
    __tablename__ = "kerberos_profiles"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    uuid       = Column(String(36), unique=True, nullable=False, default=_new_uuid)
    name       = Column(String(100), unique=True, nullable=False)
    principal  = Column(String(255), nullable=False)  # ex: "jdupont@REALM.EXAMPLE"
    password   = Column(String(255), nullable=False)  # chiffré
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_tested_at    = Column(DateTime, nullable=True)
    last_test_success = Column(Boolean, nullable=True)

    def __repr__(self):
        return f"<KerberosProfile name={self.name} principal={self.principal}>"


# ──────────────────────────────────────────────
#  PROFIL D'ÉLÉVATION (sudo su) — étape SQOOP_EXPORT
# ──────────────────────────────────────────────

class ElevationProfile(Base):
    """Élévation de privilèges (sudo su <target_user>) sur un nœud edge — étape SQOOP_EXPORT,
    pour les utilisateurs qui passent par un compte technique partagé (ex : "nifi") plutôt que
    par Kerberos. Comme KerberosProfile, ne peut pas se tester seule : requiert un SshProfile
    pour tenter réellement le sudo su (voir core/hadoop_edge.py)."""
    __tablename__ = "elevation_profiles"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    uuid        = Column(String(36), unique=True, nullable=False, default=_new_uuid)
    name        = Column(String(100), unique=True, nullable=False)
    target_user = Column(String(100), nullable=False)  # ex: "nifi"
    password    = Column(String(255), nullable=False)  # chiffré, généralement partagé par l'équipe
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_tested_at    = Column(DateTime, nullable=True)
    last_test_success = Column(Boolean, nullable=True)

    def __repr__(self):
        return f"<ElevationProfile name={self.name} target_user={self.target_user}>"


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

    # Déclenchement conditionnel après un autre pipeline (chantier P) — additif, coexiste avec
    # la planification cron ci-dessus, ne la remplace jamais. Volontairement pas transporté par
    # l'export/import (database/export_import.py) : référence un autre pipeline de premier
    # niveau, pas un profil partagé portable — voir set_pipeline_trigger() dans db_manager.py.
    trigger_after_pipeline_id = Column(Integer, ForeignKey("pipelines.id"), nullable=True)
    trigger_condition         = Column(Enum(TriggerCondition), nullable=True)

    created_at        = Column(DateTime, default=datetime.utcnow)
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    oracle_profile = relationship("OracleProfile", back_populates="pipelines")
    ftp_profile    = relationship("FtpProfile",    back_populates="pipelines")
    sql_query      = relationship("SqlQuery",      back_populates="pipelines")
    trigger_after_pipeline = relationship("Pipeline", remote_side=[id])
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
    timeout_s   = Column(Integer, default=0, nullable=False)   # 0 = aucune limite — chantier J.1
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
    # Étape en cours + log partiel, mis à jour en continu pendant l'exécution (pas seulement à
    # la fin) — visibilité d'un run en cours (chantier N). NULL une fois le run terminé.
    current_step_label = Column(String(255), nullable=True)
    # _step_key de l'étape en cours (identité stable, contrairement au libellé humain ci-dessus)
    # — permet au canevas de l'éditeur graphique de savoir PRÉCISÉMENT quel nœud surligner
    # pendant une exécution (chantier identité visuelle, traçage lumineux). NULL une fois le run
    # terminé, comme current_step_label.
    current_step_key = Column(String(255), nullable=True)

    # Reprise depuis l'échec (chantier J.2) — snapshot JSON (étapes déjà réussies, empreintes de
    # config pour détecter une modification depuis l'échec, artefacts, ports actifs) persisté
    # uniquement quand ce run échoue/est annulé ET qu'au moins une étape a réussi avant l'échec.
    # NULL = rien à reprendre (run réussi, ou état déjà consommé par une reprise/purgé).
    resumable_state_json = Column(Text, nullable=True)
    # Informatif seulement (affichage "Reprise du run #N") — pas de contrainte FK, cohérent avec
    # le reste du schéma SQLite de cette app.
    resumed_from_run_id  = Column(Integer, nullable=True)

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
    digest_time             = Column(String(5), default="07:00", nullable=False)   # "HH:MM"
    digest_day_of_week      = Column(Integer, default=0, nullable=False)  # 0=lundi (WEEKLY only)
    digest_last_sent_at     = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<NotificationSettings enabled={self.digest_enabled} frequency={self.digest_frequency}>"


# ──────────────────────────────────────────────
#  PARAMÈTRES APPLICATIFS (chantier écran "Paramètres")
# ──────────────────────────────────────────────

class AppSettings(Base):
    """
    Ligne singleton (id=1 toujours) — même patron que NotificationSettings ci-dessus. Réunit ce
    qui, jusqu'ici, était câblé en dur dans le code (fuseau horaire du scheduler, niveau de log,
    fréquences de rafraîchissement de l'UI…) sans aucun endroit pour le consulter ou le modifier
    sans reconstruire l'exe. max_concurrent_runs est stocké dès maintenant mais volontairement
    PAS ENCORE appliqué (voir ui/main_window/settings_view.py) — sa mise en application réelle
    est le premier acte d'un futur chantier dédié au suivi des ressources, pas de celui-ci.
    """
    __tablename__ = "app_settings"

    id                      = Column(Integer, primary_key=True, default=1)

    # Ordonnanceur (core/scheduler.py)
    timezone                = Column(String(64), default="UTC", nullable=False)
    misfire_grace_time_min  = Column(Integer, default=60, nullable=False)
    # Défaut = True, pas False : préserve le comportement actuellement câblé en dur
    # (core/scheduler.py) — une nouvelle colonne ne doit jamais changer le comportement
    # silencieusement pour qui n'a jamais ouvert l'écran Paramètres.
    coalesce_missed_runs    = Column(Boolean, default=True, nullable=False)
    max_concurrent_runs     = Column(Integer, default=6, nullable=False)

    # Journalisation (main.py)
    log_level               = Column(String(10), default="INFO", nullable=False)
    log_max_bytes           = Column(Integer, default=5_000_000, nullable=False)
    log_backup_count        = Column(Integer, default=5, nullable=False)

    # Rafraîchissement de l'interface
    dashboard_refresh_s     = Column(Integer, default=30, nullable=False)
    pipelines_refresh_s     = Column(Integer, default=30, nullable=False)
    live_log_refresh_s      = Column(Integer, default=2, nullable=False)
    trace_glow_refresh_s    = Column(Integer, default=1, nullable=False)

    def __repr__(self):
        return f"<AppSettings timezone={self.timezone} max_concurrent_runs={self.max_concurrent_runs}>"


# ──────────────────────────────────────────────
#  JOURNAL D'AUDIT (modifications de pipeline, exports, imports)
# ──────────────────────────────────────────────

class AuditEvent(Base):
    """
    Trace append-only des opérations structurantes — pas un doublon du fichier de log
    applicatif (bruit technique, non persistant avant ce chantier) : ici seulement ce qui
    compte pour un audit (qui a modifié/exporté/importé quoi, quand). Pas de FK stricte sur
    pipeline_id : doit rester lisible même après suppression du pipeline concerné, d'où le
    snapshot pipeline_name pris au moment de l'événement.
    """
    __tablename__ = "audit_events"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    timestamp     = Column(DateTime, default=datetime.utcnow)
    event_type    = Column(String(50), nullable=False)
    pipeline_id   = Column(Integer, nullable=True)
    pipeline_name = Column(String(100), nullable=True)
    actor         = Column(String(100), nullable=True)   # getpass.getuser() — pas de notion de rôle/permission, juste une trace
    detail        = Column(Text, nullable=True)

    def __repr__(self):
        return f"<AuditEvent {self.event_type} pipeline={self.pipeline_name!r} actor={self.actor!r}>"