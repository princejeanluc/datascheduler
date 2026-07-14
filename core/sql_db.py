"""
DataScheduler — core/sql_db.py
Connecteur générique multi-moteurs (Oracle, MySQL, PostgreSQL, SQL Server) bâti sur
SQLAlchemy — utilisé par les steps DB_EXTRACT / DB_EXECUTE / DB_LOAD.

Oracle garde son propre profil (OracleProfile, core/oracle.py) pour ses champs
spécifiques (service_name/sid/auth_mode) et le bouton "Tester" de son dialogue de profil,
mais passe par ce même connecteur générique à l'exécution d'un step — un seul code de
connexion/export/chargement à maintenir, quel que soit le moteur.
"""

import csv
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import create_engine, text

from core.oracle import is_plsql_block  # noqa: F401 — réexporté pour core/steps/db_execute.py

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  DATACLASS DE CONFIGURATION
# ──────────────────────────────────────────────

@dataclass
class SqlDbConfig:
    db_type:       str
    host:          str
    port:          int
    username:      str
    password:      str
    # Oracle uniquement
    service_name:  str | None = None
    sid:           str | None = None
    auth_mode:     str        = "DEFAULT"
    # MySQL / PostgreSQL / SQL Server
    database_name: str | None = None
    extra:         dict       = field(default_factory=dict)


def get_profile_object(db_type: str, profile_id: int):
    """Récupère l'objet profil (OracleProfile ou DatabaseProfile) selon db_type."""
    from database import db_manager as db
    if db_type == "ORACLE":
        return db.get_oracle_profile(profile_id)
    return db.get_database_profile(profile_id)


def config_from_profile(db_type: str, profile) -> SqlDbConfig:
    """
    Construit un SqlDbConfig depuis un OracleProfile ou un DatabaseProfile SQLAlchemy,
    selon db_type.
    """
    if db_type == "ORACLE":
        return SqlDbConfig(
            db_type=db_type, host=profile.host, port=profile.port,
            username=profile.username, password=profile.password,
            service_name=profile.service_name, sid=profile.sid,
            auth_mode=getattr(profile, "auth_mode", "DEFAULT") or "DEFAULT",
        )
    extra = {}
    if getattr(profile, "extra_json", None):
        try:
            extra = json.loads(profile.extra_json)
        except ValueError:
            extra = {}
    return SqlDbConfig(
        db_type=db_type, host=profile.host, port=profile.port,
        username=profile.username, password=profile.password,
        database_name=profile.database_name, extra=extra,
    )


# ──────────────────────────────────────────────
#  CONSTRUCTION DE L'URL SQLALCHEMY
# ──────────────────────────────────────────────

def _detect_mssql_odbc_driver() -> str | None:
    """
    Retourne le nom du driver ODBC SQL Server le plus récent installé sur la machine,
    ou None si aucun n'est disponible (le pilote pymssql prend alors le relais —
    aucune installation supplémentaire requise dans ce cas).
    """
    try:
        import pyodbc
    except ImportError:
        return None
    try:
        installed = pyodbc.drivers()
    except Exception:
        return None
    for wanted in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"):
        if wanted in installed:
            return wanted
    candidates = [d for d in installed if "SQL Server" in d]
    return candidates[0] if candidates else None


def build_engine_url(config: SqlDbConfig) -> str:
    """Construit l'URL de connexion SQLAlchemy adaptée au moteur."""
    user = quote_plus(config.username)
    pwd  = quote_plus(config.password)

    if config.db_type == "ORACLE":
        if config.service_name:
            return f"oracle+oracledb://{user}:{pwd}@{config.host}:{config.port}/?service_name={config.service_name}"
        if config.sid:
            return f"oracle+oracledb://{user}:{pwd}@{config.host}:{config.port}/{config.sid}"
        raise ValueError("Profil Oracle : service_name ou sid obligatoire.")

    if config.db_type == "MYSQL":
        return f"mysql+pymysql://{user}:{pwd}@{config.host}:{config.port}/{config.database_name or ''}"

    if config.db_type == "POSTGRESQL":
        return f"postgresql+psycopg2://{user}:{pwd}@{config.host}:{config.port}/{config.database_name or ''}"

    if config.db_type == "SQLSERVER":
        db = config.database_name or ""
        driver = _detect_mssql_odbc_driver()
        if driver:
            return (f"mssql+pyodbc://{user}:{pwd}@{config.host}:{config.port}/{db}"
                    f"?driver={quote_plus(driver)}")
        return f"mssql+pymssql://{user}:{pwd}@{config.host}:{config.port}/{db}"

    raise ValueError(f"Moteur de base de données inconnu : {config.db_type!r}")


# ──────────────────────────────────────────────
#  RÉSULTATS
# ──────────────────────────────────────────────

@dataclass
class ConnectionTestResult:
    success:  bool
    message:  str
    duration_ms: float | None = None


@dataclass
class ExportResult:
    success:       bool
    rows_exported: int         = 0
    output_path:   Path | None = None
    error:         str | None  = None
    duration_s:    float       = 0.0
    chunks_count:  int         = 0


@dataclass
class LoadResult:
    success:       bool
    rows_loaded:   int         = 0
    error:         str | None  = None
    duration_s:    float       = 0.0
    chunks_count:  int         = 0


# ──────────────────────────────────────────────
#  CONNEXION GÉNÉRIQUE
# ──────────────────────────────────────────────

class SqlConnector:
    """Gère une connexion à n'importe quel moteur supporté via un moteur SQLAlchemy."""

    def __init__(self, config: SqlDbConfig):
        self.config = config
        self._engine = None
        self._connection = None

    def connect(self) -> None:
        url = build_engine_url(self.config)
        connect_args = {}
        if self.config.db_type == "ORACLE" and self.config.auth_mode != "DEFAULT":
            import oracledb
            mode_map = {
                "SYSDBA":  oracledb.AUTH_MODE_SYSDBA,
                "SYSOPER": oracledb.AUTH_MODE_SYSOPER,
            }
            connect_args["mode"] = mode_map.get(self.config.auth_mode, oracledb.AUTH_MODE_DEFAULT)

        logger.info("Connexion %s : %s@%s:%s", self.config.db_type,
                    self.config.username, self.config.host, self.config.port)
        self._engine = create_engine(url, connect_args=connect_args)
        self._connection = self._engine.connect()
        logger.info("Connexion %s établie.", self.config.db_type)

    def disconnect(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception as e:
                logger.warning("Erreur fermeture connexion : %s", e)
            finally:
                self._connection = None
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()

    def test_connection(self) -> ConnectionTestResult:
        """Tente une connexion, ne lève pas d'exception — adapté pour l'UI."""
        start = datetime.utcnow()
        try:
            self.connect()
            duration = (datetime.utcnow() - start).total_seconds() * 1000
            return ConnectionTestResult(
                success=True, message="Connexion réussie.",
                duration_ms=round(duration, 1),
            )
        except Exception as e:
            duration = (datetime.utcnow() - start).total_seconds() * 1000
            return ConnectionTestResult(
                success=False, message=str(e), duration_ms=round(duration, 1),
            )
        finally:
            self.disconnect()

    @property
    def connection(self):
        if self._connection is None:
            raise RuntimeError("Non connecté. Appelle connect() d'abord.")
        return self._connection

    @property
    def engine(self):
        if self._engine is None:
            raise RuntimeError("Non connecté. Appelle connect() d'abord.")
        return self._engine


# ──────────────────────────────────────────────
#  EXPORT CSV PAR CHUNKS
# ──────────────────────────────────────────────

class SqlExporter:
    """Exporte le résultat d'une requête SQL vers un fichier CSV, en flux (chunked)."""

    _QUOTING_MAP = {
        "QUOTE_MINIMAL":    csv.QUOTE_MINIMAL,
        "QUOTE_ALL":        csv.QUOTE_ALL,
        "QUOTE_NONNUMERIC": csv.QUOTE_NONNUMERIC,
        "QUOTE_NONE":       csv.QUOTE_NONE,
    }

    def __init__(
        self,
        connector:   SqlConnector,
        sql:         str,
        output_path: Path,
        separator:   str = ";",
        encoding:    str = "utf-8-sig",
        chunk_size:  int = 50_000,
        quoting:     str = "QUOTE_NONNUMERIC",
        on_progress: Callable[[int, int], None] | None = None,
    ):
        self.connector   = connector
        self.sql         = sql
        self.output_path = Path(output_path)
        self.separator   = separator
        self.encoding    = encoding
        self.chunk_size  = chunk_size
        self.quoting     = self._QUOTING_MAP.get(quoting, csv.QUOTE_NONNUMERIC)
        self.on_progress = on_progress

    def export(self) -> ExportResult:
        start = datetime.utcnow()
        rows_total  = 0
        chunk_index = 0

        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.output_path, "w", newline="",
                      encoding=self.encoding) as csv_file:

                chunk_iter: Iterator[pd.DataFrame] = pd.read_sql(
                    self.sql,
                    self.connector.connection,
                    chunksize=self.chunk_size,
                )

                first_chunk = True
                for chunk in chunk_iter:
                    to_csv_kwargs = dict(
                        sep=self.separator,
                        index=False,
                        header=first_chunk,
                        quoting=self.quoting,
                    )
                    if self.quoting == csv.QUOTE_NONE:
                        to_csv_kwargs["escapechar"] = "\\"
                    chunk.to_csv(csv_file, **to_csv_kwargs)
                    first_chunk = False
                    rows_total  += len(chunk)
                    chunk_index += 1

                    if self.on_progress:
                        self.on_progress(rows_total, chunk_index)

            duration = (datetime.utcnow() - start).total_seconds()
            logger.info("Export terminé : %d lignes en %.1fs → %s",
                        rows_total, duration, self.output_path)

            return ExportResult(
                success=True, rows_exported=rows_total,
                output_path=self.output_path,
                duration_s=round(duration, 2), chunks_count=chunk_index,
            )

        except Exception as e:
            logger.error("Erreur export CSV : %s", e)
            return ExportResult(success=False, error=str(e))


# ──────────────────────────────────────────────
#  CHARGEMENT CSV → TABLE
# ──────────────────────────────────────────────

class SqlLoader:
    """
    Charge un fichier CSV dans une table via pandas.DataFrame.to_sql() par chunks —
    to_sql gère nativement la syntaxe d'insertion propre à chaque moteur, pas besoin de
    construire les instructions INSERT à la main (contrairement à l'ancien OracleLoader).
    """

    def __init__(
        self,
        connector:   SqlConnector,
        csv_path:    Path,
        table_name:  str,
        separator:   str = ";",
        encoding:    str = "utf-8-sig",
        chunk_size:  int = 50_000,
        truncate_before_load: bool = False,
        on_progress: Callable[[int, int], None] | None = None,
    ):
        self.connector   = connector
        self.csv_path    = Path(csv_path)
        self.table_name  = table_name
        self.separator   = separator
        self.encoding    = encoding
        self.chunk_size  = chunk_size
        self.truncate_before_load = truncate_before_load
        self.on_progress = on_progress

    def load(self) -> LoadResult:
        start = datetime.utcnow()
        rows_total  = 0
        chunk_index = 0

        try:
            if self.truncate_before_load:
                self.connector.connection.execute(text(f"TRUNCATE TABLE {self.table_name}"))
                self.connector.connection.commit()

            for chunk in pd.read_csv(self.csv_path, sep=self.separator,
                                      encoding=self.encoding, chunksize=self.chunk_size):
                chunk.to_sql(self.table_name, self.connector.engine,
                             if_exists="append", index=False)
                rows_total  += len(chunk)
                chunk_index += 1
                if self.on_progress:
                    self.on_progress(rows_total, chunk_index)

            duration = (datetime.utcnow() - start).total_seconds()
            logger.info("Chargement terminé : %d lignes en %.1fs → %s",
                        rows_total, duration, self.table_name)

            return LoadResult(
                success=True, rows_loaded=rows_total,
                duration_s=round(duration, 2), chunks_count=chunk_index,
            )

        except Exception as e:
            logger.error("Erreur chargement CSV : %s", e)
            return LoadResult(success=False, error=str(e))
