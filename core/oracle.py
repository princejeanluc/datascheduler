"""
DataScheduler — core/oracle.py
Gestion des connexions Oracle et export CSV par chunks.

Dépendances : oracledb, pandas
"""

import csv
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Generator, Iterator

import oracledb
import pandas as pd

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  DATACLASS DE CONFIGURATION
# ──────────────────────────────────────────────

# Modes d'authentification exposés (miroir des constantes oracledb)
AUTH_MODE_DEFAULT = "DEFAULT"   # utilisateur normal
AUTH_MODE_SYSDBA  = "SYSDBA"   # requis pour SYS en SYSDBA
AUTH_MODE_SYSOPER = "SYSOPER"  # requis pour SYS en SYSOPER

AUTH_MODES = [AUTH_MODE_DEFAULT, AUTH_MODE_SYSDBA, AUTH_MODE_SYSOPER]


def _resolve_auth_mode(mode: str):
    """Traduit notre constante string vers la constante oracledb."""
    mapping = {
        AUTH_MODE_DEFAULT: oracledb.AUTH_MODE_DEFAULT,
        AUTH_MODE_SYSDBA:  oracledb.AUTH_MODE_SYSDBA,
        AUTH_MODE_SYSOPER: oracledb.AUTH_MODE_SYSOPER,
    }
    return mapping.get(mode, oracledb.AUTH_MODE_DEFAULT)


@dataclass
class OracleConfig:
    """Représente un profil de connexion Oracle."""
    host:         str
    port:         int
    username:     str
    password:     str
    service_name: str | None = None   # préféré sur le SID
    sid:          str | None = None
    encoding:     str        = "UTF-8"
    auth_mode:    str        = AUTH_MODE_DEFAULT  # DEFAULT | SYSDBA | SYSOPER

    def dsn(self) -> str:
        """Construit le DSN oracledb selon service_name ou SID."""
        if self.service_name:
            return oracledb.makedsn(self.host, self.port,
                                    service_name=self.service_name)
        if self.sid:
            return oracledb.makedsn(self.host, self.port, sid=self.sid)
        raise ValueError("OracleConfig : service_name ou sid obligatoire.")

    def oracledb_mode(self):
        """Retourne la constante oracledb correspondant à auth_mode."""
        return _resolve_auth_mode(self.auth_mode)


# ──────────────────────────────────────────────
#  RÉSULTAT DE TEST DE CONNEXION
# ──────────────────────────────────────────────

@dataclass
class ConnectionTestResult:
    success:  bool
    message:  str
    db_version: str | None = None
    duration_ms: float | None = None


# ──────────────────────────────────────────────
#  RÉSULTAT D'EXPORT
# ──────────────────────────────────────────────

@dataclass
class ExportResult:
    success:       bool
    rows_exported: int         = 0
    output_path:   Path | None = None
    error:         str | None  = None
    duration_s:    float       = 0.0
    chunks_count:  int         = 0


# ──────────────────────────────────────────────
#  CONNEXION ORACLE
# ──────────────────────────────────────────────

class OracleConnector:
    """
    Gère une connexion Oracle avec oracledb en mode thin
    (pas besoin d'Oracle Instant Client).
    """

    def __init__(self, config: OracleConfig):
        self.config = config
        self._connection: oracledb.Connection | None = None

    # ── Connexion / déconnexion ──────────────

    def connect(self) -> None:
        """Ouvre la connexion. Lève une exception si échec."""
        logger.info("Connexion Oracle : %s@%s:%s",
                    self.config.username, self.config.host, self.config.port)
        self._connection = oracledb.connect(
            user=self.config.username,
            password=self.config.password,
            dsn=self.config.dsn(),
            mode=self.config.oracledb_mode(),
        )
        logger.info("Connexion Oracle établie (version : %s)",
                    self._connection.version)

    def disconnect(self) -> None:
        """Ferme proprement la connexion."""
        if self._connection:
            try:
                self._connection.close()
                logger.info("Connexion Oracle fermée.")
            except Exception as e:
                logger.warning("Erreur fermeture Oracle : %s", e)
            finally:
                self._connection = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()

    # ── Test de connexion ────────────────────

    def test_connection(self) -> ConnectionTestResult:
        """
        Tente une connexion, renvoie un ConnectionTestResult.
        Ne lève pas d'exception — adapté pour l'UI.
        """
        start = datetime.utcnow()
        try:
            with oracledb.connect(
                user=self.config.username,
                password=self.config.password,
                dsn=self.config.dsn(),
                mode=self.config.oracledb_mode(),
            ) as conn:
                duration = (datetime.utcnow() - start).total_seconds() * 1000
                return ConnectionTestResult(
                    success=True,
                    message="Connexion réussie.",
                    db_version=conn.version,
                    duration_ms=round(duration, 1),
                )
        except oracledb.DatabaseError as e:
            duration = (datetime.utcnow() - start).total_seconds() * 1000
            return ConnectionTestResult(
                success=False,
                message=f"Erreur Oracle : {e}",
                duration_ms=round(duration, 1),
            )
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                message=f"Erreur inattendue : {e}",
            )

    # ── Propriété connexion ──────────────────

    @property
    def connection(self) -> oracledb.Connection:
        if not self._connection:
            raise RuntimeError("Non connecté. Appelle connect() d'abord.")
        return self._connection


# ──────────────────────────────────────────────
#  EXPORT CSV PAR CHUNKS
# ──────────────────────────────────────────────

class OracleExporter:
    """
    Exporte le résultat d'une requête SQL vers un fichier CSV.

    Utilise pandas.read_sql en mode chunked pour ne jamais charger
    l'intégralité des données en RAM.

    Paramètres :
        connector   : OracleConnector connecté
        sql         : requête SELECT
        output_path : chemin du fichier CSV de sortie
        separator   : séparateur CSV (défaut : ;)
        encoding    : encodage CSV (défaut : utf-8-sig pour Excel)
        chunk_size  : nombre de lignes par chunk (défaut : 50 000)
        on_progress : callback(rows_done, chunk_index) pour la progressbar UI
    """

    # Correspondance nom → constante csv
    _QUOTING_MAP = {
        "QUOTE_MINIMAL":    csv.QUOTE_MINIMAL,
        "QUOTE_ALL":        csv.QUOTE_ALL,
        "QUOTE_NONNUMERIC": csv.QUOTE_NONNUMERIC,
        "QUOTE_NONE":       csv.QUOTE_NONE,
    }

    def __init__(
        self,
        connector:   OracleConnector,
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
        """
        Lance l'export. Renvoie un ExportResult.
        Ne lève pas d'exception — adapté pour l'UI et le scheduler.
        """
        start = datetime.utcnow()
        rows_total  = 0
        chunk_index = 0

        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.output_path, "w", newline="",
                      encoding=self.encoding) as csv_file:

                writer = None  # on écrira le header au premier chunk

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

                    logger.debug("Chunk %d exporté — %d lignes au total",
                                 chunk_index, rows_total)

                    if self.on_progress:
                        self.on_progress(rows_total, chunk_index)

            duration = (datetime.utcnow() - start).total_seconds()
            logger.info("Export terminé : %d lignes en %.1fs → %s",
                        rows_total, duration, self.output_path)

            return ExportResult(
                success=True,
                rows_exported=rows_total,
                output_path=self.output_path,
                duration_s=round(duration, 2),
                chunks_count=chunk_index,
            )

        except oracledb.DatabaseError as e:
            logger.error("Erreur Oracle durant l'export : %s", e)
            return ExportResult(success=False, error=f"Erreur Oracle : {e}")
        except Exception as e:
            logger.error("Erreur export CSV : %s", e)
            return ExportResult(success=False, error=str(e))


# ──────────────────────────────────────────────
#  RÉSULTAT DE CHARGEMENT
# ──────────────────────────────────────────────

@dataclass
class LoadResult:
    success:       bool
    rows_loaded:   int         = 0
    error:         str | None  = None
    duration_s:    float       = 0.0
    chunks_count:  int         = 0


# ──────────────────────────────────────────────
#  CHARGEMENT CSV → TABLE ORACLE
# ──────────────────────────────────────────────

class OracleLoader:
    """
    Charge un fichier CSV dans une table Oracle via INSERT par chunks
    (cursor.executemany). Les colonnes du CSV doivent correspondre
    aux noms de colonnes de la table cible (association simple par en-tête).

    Paramètres :
        connector   : OracleConnector connecté
        csv_path    : chemin du fichier CSV source
        table_name  : table Oracle cible
        separator   : séparateur CSV (défaut : ;)
        encoding    : encodage CSV (défaut : utf-8-sig)
        chunk_size  : nombre de lignes par chunk (défaut : 50 000)
        truncate_before_load : si True, TRUNCATE TABLE avant le premier chunk
        on_progress : callback(rows_done, chunk_index) pour la progressbar UI
    """

    def __init__(
        self,
        connector:   OracleConnector,
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
        """
        Lance le chargement. Renvoie un LoadResult.
        Ne lève pas d'exception — adapté pour l'UI et le scheduler.
        """
        start = datetime.utcnow()
        rows_total  = 0
        chunk_index = 0

        try:
            cursor = self.connector.connection.cursor()

            if self.truncate_before_load:
                cursor.execute(f"TRUNCATE TABLE {self.table_name}")

            chunk_iter: Iterator[pd.DataFrame] = pd.read_csv(
                self.csv_path,
                sep=self.separator,
                encoding=self.encoding,
                chunksize=self.chunk_size,
            )

            insert_sql = None
            for chunk in chunk_iter:
                if insert_sql is None:
                    columns    = list(chunk.columns)
                    placeholders = ", ".join(f":{i + 1}" for i in range(len(columns)))
                    insert_sql = (
                        f"INSERT INTO {self.table_name} ({', '.join(columns)}) "
                        f"VALUES ({placeholders})"
                    )

                clean = chunk.astype(object).where(chunk.notnull(), None)
                rows  = [tuple(row) for row in clean.itertuples(index=False)]
                cursor.executemany(insert_sql, rows)
                self.connector.connection.commit()

                rows_total  += len(rows)
                chunk_index += 1

                logger.debug("Chunk %d chargé — %d lignes au total",
                             chunk_index, rows_total)

                if self.on_progress:
                    self.on_progress(rows_total, chunk_index)

            duration = (datetime.utcnow() - start).total_seconds()
            logger.info("Chargement terminé : %d lignes en %.1fs → %s",
                        rows_total, duration, self.table_name)

            return LoadResult(
                success=True,
                rows_loaded=rows_total,
                duration_s=round(duration, 2),
                chunks_count=chunk_index,
            )

        except oracledb.DatabaseError as e:
            logger.error("Erreur Oracle durant le chargement : %s", e)
            return LoadResult(success=False, error=f"Erreur Oracle : {e}")
        except Exception as e:
            logger.error("Erreur chargement CSV : %s", e)
            return LoadResult(success=False, error=str(e))


# ──────────────────────────────────────────────
#  HELPER : construire depuis un profil DB
# ──────────────────────────────────────────────

def config_from_profile(profile) -> OracleConfig:
    """
    Construit un OracleConfig depuis un OracleProfile SQLAlchemy.
    Utilisation :
        cfg = config_from_profile(db_profile)
        connector = OracleConnector(cfg)
    """
    return OracleConfig(
        host=profile.host,
        port=profile.port,
        username=profile.username,
        password=profile.password,
        service_name=profile.service_name,
        sid=profile.sid,
        auth_mode=getattr(profile, "auth_mode", "DEFAULT") or "DEFAULT",
    )


# ──────────────────────────────────────────────
#  HELPER : détection bloc PL/SQL vs DML direct
# ──────────────────────────────────────────────

def is_plsql_block(sql_text: str) -> bool:
    """
    Détecte un bloc PL/SQL (anonyme "BEGIN ... END;" ou "DECLARE ...") plutôt qu'une
    instruction DML/DDL directe.

    Important pour l'interprétation de cursor.rowcount : pour un bloc PL/SQL, oracledb ne
    remonte que le résultat de l'appel du bloc lui-même — pas le nombre de lignes affectées
    par une instruction DML exécutée à l'intérieur (typiquement un INSERT/UPDATE fait par une
    procédure stockée appelée depuis le bloc). rowcount reste alors à 0 même si des lignes ont
    bien été insérées/modifiées côté base.
    """
    head = sql_text.strip().upper()
    return head.startswith("BEGIN") or head.startswith("DECLARE")


# ──────────────────────────────────────────────
#  HELPER : résolution des templates de nom
# ──────────────────────────────────────────────

def resolve_template(template: str, dt: datetime | None = None) -> str:
    """
    Remplace les tokens de date dans un template.

    Tokens supportés :
        {yyyy}   → 2026
        {yy}     → 26
        {MM}     → 06
        {dd}     → 08
        {HH}     → 14
        {mm}     → 30
        {ss}     → 00
        {yyyyMMdd}    → 20260608
        {yyyyMMddHHmm}→ 202606081430

    Exemple :
        resolve_template("ventes_{yyyyMMdd}.csv")
        → "ventes_20260608.csv"
    """
    d = dt or datetime.now()

    replacements = {
        "{yyyyMMddHHmm}": d.strftime("%Y%m%d%H%M"),
        "{yyyyMMdd}":     d.strftime("%Y%m%d"),
        "{yyyy}":         d.strftime("%Y"),
        "{yy}":           d.strftime("%y"),
        "{MM}":           d.strftime("%m"),
        "{dd}":           d.strftime("%d"),
        "{HH}":           d.strftime("%H"),
        "{mm}":           d.strftime("%M"),
        "{ss}":           d.strftime("%S"),
    }

    result = template
    for token, value in replacements.items():
        result = result.replace(token, value)
    return result