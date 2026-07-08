"""
DataScheduler — core/steps/oracle_extract.py
Étape : connexion Oracle, exécution SQL, export CSV vers fichier temporaire.
"""

import tempfile
from pathlib import Path

from .base import BaseStep, StepContext, StepResult


class OracleExtractStep(BaseStep):
    PRODUCES = {"output_file"}

    def run(self, ctx: StepContext, on_progress=None) -> StepResult:
        result = StepResult()

        def progress(msg: str, pct: int):
            if on_progress:
                on_progress(msg, pct)

        try:
            from database import db_manager as db
            from core.oracle import OracleConnector, OracleExporter, config_from_profile

            oracle_id = self.config.get("oracle_profile_id")
            query_id  = self.config.get("sql_query_id")

            oracle_profile = db.get_oracle_profile(oracle_id)
            sql_query      = db.get_sql_query(query_id)

            if not oracle_profile:
                result.error = f"Profil Oracle ID {oracle_id} introuvable."
                return result
            if not sql_query:
                result.error = f"Requête SQL ID {query_id} introuvable."
                return result

            ctx.log(f"Connexion Oracle : {oracle_profile.host}:{oracle_profile.port}")
            progress("Connexion Oracle…", 10)

            oracle_cfg = config_from_profile(oracle_profile)
            connector  = OracleConnector(oracle_cfg)
            connector.connect()
            ctx.log("Connexion Oracle : OK")

            tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, prefix="ds_")
            tmp_path = Path(tmp.name)
            tmp.close()

            rows_done = [0]

            def export_progress(rows: int, chunk_idx: int):
                rows_done[0] = rows
                progress(f"Export… {rows:,} lignes", min(25 + chunk_idx * 2, 75))

            exporter = OracleExporter(
                connector=connector,
                sql=sql_query.sql_text,
                output_path=tmp_path,
                separator=self.config.get("csv_separator",  ";"),
                encoding=self.config.get("csv_encoding",    "utf-8-sig"),
                chunk_size=self.config.get("csv_chunk_size", 50000),
                quoting=self.config.get("csv_quoting",      "QUOTE_NONNUMERIC"),
                on_progress=export_progress,
            )
            export_result = exporter.export()
            connector.disconnect()

            if not export_result.success:
                result.error = f"Export CSV : {export_result.error}"
                return result

            ctx.output_file = tmp_path
            ctx.rows_count  = export_result.rows_exported
            ctx.log(
                f"Export CSV : OK — {export_result.rows_exported:,} lignes "
                f"en {export_result.duration_s:.1f}s ({export_result.chunks_count} chunks)"
            )
            result.success = True

        except Exception as e:
            result.error = str(e)

        return result
