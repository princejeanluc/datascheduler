"""
DataScheduler — core/pipeline.py
Exécution d'un pipeline complet : Oracle → CSV (tmp) → FTP → nettoyage.

Ce module est appelé par le scheduler. Il est aussi appelable manuellement
depuis l'UI (bouton "Exécuter maintenant").
"""

import logging
import tempfile
from datetime import datetime
from pathlib import Path

from core.oracle import (
    OracleConnector, OracleExporter,
    config_from_profile as oracle_config_from_profile,
)
from core.ftp import (
    FtpUploader,
    config_from_profile as ftp_config_from_profile,
    resolve_remote_path,
)
from database import db_manager as db

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  RÉSULTAT D'EXÉCUTION
# ──────────────────────────────────────────────

class PipelineResult:
    def __init__(self):
        self.success       = False
        self.rows_exported = 0
        self.remote_path   = None
        self.error         = None
        self.log_lines     = []
        self.started_at    = datetime.utcnow()
        self.finished_at   = None

    def log(self, msg: str):
        ts = datetime.utcnow().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        self.log_lines.append(line)
        logger.info(msg)

    def fail(self, msg: str):
        self.error = msg
        self.log(f"ERREUR : {msg}")

    def finish(self):
        self.finished_at = datetime.utcnow()

    @property
    def duration_s(self) -> float:
        if self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return 0.0

    @property
    def log_text(self) -> str:
        return "\n".join(self.log_lines)


# ──────────────────────────────────────────────
#  EXÉCUTEUR DE PIPELINE
# ──────────────────────────────────────────────

def run_pipeline(
    pipeline_id: int,
    on_progress=None,   # callback(step: str, pct: int) pour l'UI
) -> PipelineResult:
    """
    Exécute un pipeline complet :
      1. Charge la config depuis la DB
      2. Connexion Oracle
      3. Export CSV (chunks) vers fichier temporaire
      4. Upload FTP
      5. Nettoyage du fichier tmp
      6. Mise à jour DB (statut, durée, lignes)

    Paramètres :
        pipeline_id : ID du pipeline en base
        on_progress : callback(step, pct) pour alimenter une progressbar UI

    Retourne un PipelineResult (ne lève jamais d'exception).
    """
    result = PipelineResult()
    run_id = None

    def progress(step: str, pct: int):
        if on_progress:
            on_progress(step, pct)

    try:
        # ── Étape 0 : charger le pipeline ────────
        progress("Chargement…", 0)
        pipeline = db.get_pipeline(pipeline_id)
        if not pipeline:
            result.fail(f"Pipeline ID {pipeline_id} introuvable en base.")
            result.finish()
            return result

        result.log(f"Pipeline : {pipeline.name}")

        oracle_profile = db.get_oracle_profile(pipeline.oracle_profile_id)
        ftp_profile    = db.get_ftp_profile(pipeline.ftp_profile_id)
        sql_query      = db.get_sql_query(pipeline.sql_query_id)

        if not oracle_profile:
            result.fail("Profil Oracle introuvable.")
            result.finish(); return result
        if not ftp_profile:
            result.fail("Profil FTP introuvable.")
            result.finish(); return result
        if not sql_query:
            result.fail("Requête SQL introuvable.")
            result.finish(); return result

        # ── Enregistrement du RUN en base ────────
        run = db.create_run(pipeline_id)
        run_id = run.id
        result.log(f"Run ID : {run_id}")
        _update_pipeline_status(pipeline_id, "RUNNING")

        # ── Étape 1 : connexion Oracle ────────────
        progress("Connexion Oracle…", 10)
        result.log(f"Connexion Oracle : {oracle_profile.host}:{oracle_profile.port}")
        oracle_cfg   = oracle_config_from_profile(oracle_profile)
        connector    = OracleConnector(oracle_cfg)
        connector.connect()
        result.log("Connexion Oracle : OK")

        # ── Étape 2 : export CSV vers tmp ─────────
        progress("Export CSV…", 25)
        result.log(f"Requête : {sql_query.name}")
        result.log(f"Chunk size : {pipeline.csv_chunk_size} lignes")

        tmp_file = tempfile.NamedTemporaryFile(
            suffix=".csv", delete=False,
            prefix=f"ds_{pipeline.name}_"
        )
        tmp_path = Path(tmp_file.name)
        tmp_file.close()

        rows_done = [0]

        def export_progress(rows, chunk_idx):
            rows_done[0] = rows
            pct = min(25 + int(chunk_idx * 2), 75)   # 25 → 75 %
            progress(f"Export… {rows:,} lignes", pct)

        exporter = OracleExporter(
            connector=connector,
            sql=sql_query.sql_text,
            output_path=tmp_path,
            separator=pipeline.csv_separator,
            encoding=pipeline.csv_encoding,
            chunk_size=pipeline.csv_chunk_size,
            quoting=getattr(pipeline, "csv_quoting", "QUOTE_NONNUMERIC"),
            on_progress=export_progress,
        )
        export_result = exporter.export()
        connector.disconnect()

        if not export_result.success:
            result.fail(f"Export CSV échoué : {export_result.error}")
            _update_run(run_id, "FAILED", result)
            result.finish(); return result

        result.rows_exported = export_result.rows_exported
        result.log(
            f"Export CSV : OK — {export_result.rows_exported:,} lignes "
            f"en {export_result.duration_s:.1f}s "
            f"({export_result.chunks_count} chunks)"
        )

        # ── Étape 3 : upload FTP ──────────────────
        progress("Upload FTP…", 80)
        remote_full = resolve_remote_path(
            pipeline.remote_path_tpl,
            pipeline.filename_tpl,
        )
        result.log(f"Upload FTP : {ftp_profile.host} → {remote_full}")

        ftp_cfg  = ftp_config_from_profile(ftp_profile)
        uploader = FtpUploader(ftp_cfg)
        upload_result = uploader.upload(tmp_path, remote_full)

        if not upload_result.success:
            result.fail(f"Upload FTP échoué : {upload_result.error}")
            _update_run(run_id, "FAILED", result)
            result.finish(); return result

        result.remote_path = upload_result.remote_path
        result.log(
            f"Upload FTP : OK — {upload_result.bytes_sent / 1024:.1f} Ko "
            f"en {upload_result.duration_s:.1f}s"
        )

        # ── Étape 4 : nettoyage tmp ───────────────
        try:
            tmp_path.unlink()
            result.log("Fichier temporaire supprimé.")
        except Exception as e:
            result.log(f"Avertissement : impossible de supprimer le tmp : {e}")

        # ── Succès ────────────────────────────────
        result.success = True
        result.finish()
        progress("Terminé ✓", 100)
        result.log(
            f"Pipeline terminé en {result.duration_s:.1f}s — "
            f"{result.rows_exported:,} lignes exportées."
        )
        _update_run(run_id, "SUCCESS", result)
        _update_pipeline_status(pipeline_id, "SUCCESS")
        return result

    except Exception as e:
        result.fail(f"Exception inattendue : {e}")
        result.finish()
        if run_id:
            _update_run(run_id, "FAILED", result)
        _update_pipeline_status(pipeline_id, "FAILED")
        logger.exception("Erreur pipeline %s", pipeline_id)
        return result


# ──────────────────────────────────────────────
#  HELPERS DB
# ──────────────────────────────────────────────

def _update_run(run_id: int, status: str, result: PipelineResult):
    db.finish_run(
        run_id,
        status=status,
        rows_exported=result.rows_exported,
        remote_path=result.remote_path,
        error_message=result.error,
        log_text=result.log_text,
    )


def _update_pipeline_status(pipeline_id: int, status: str):
    with db.get_session() as s:
        from database.models import Pipeline
        p = s.get(Pipeline, pipeline_id)
        if p:
            p.last_status = status
            p.last_run_at = datetime.utcnow()