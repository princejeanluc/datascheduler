"""
DataScheduler — core/steps/oracle_load.py
Étape : chargement du fichier de contexte (CSV) vers une table Oracle
(association simple par en-tête CSV).
"""

from .base import BaseStep, StepContext, StepResult


class OracleLoadStep(BaseStep):

    def run(self, ctx: StepContext, on_progress=None) -> StepResult:
        result = StepResult()

        def progress(msg: str, pct: int):
            if on_progress:
                on_progress(msg, pct)

        try:
            from database import db_manager as db
            from core.oracle import OracleConnector, OracleLoader, config_from_profile

            if not ctx.output_file or not ctx.output_file.exists():
                result.error = "Aucun fichier source disponible dans le contexte."
                return result

            oracle_id  = self.config.get("oracle_profile_id")
            table_name = self.config.get("table_name", "")

            oracle_profile = db.get_oracle_profile(oracle_id)
            if not oracle_profile:
                result.error = f"Profil Oracle ID {oracle_id} introuvable."
                return result
            if not table_name:
                result.error = "Table cible non configurée."
                return result

            ctx.log(f"Connexion Oracle : {oracle_profile.host}:{oracle_profile.port}")
            progress("Connexion Oracle…", 10)

            oracle_cfg = config_from_profile(oracle_profile)
            connector  = OracleConnector(oracle_cfg)
            connector.connect()
            ctx.log("Connexion Oracle : OK")

            rows_done = [0]

            def load_progress(rows: int, chunk_idx: int):
                rows_done[0] = rows
                progress(f"Chargement… {rows:,} lignes", min(25 + chunk_idx * 2, 90))

            loader = OracleLoader(
                connector=connector,
                csv_path=ctx.output_file,
                table_name=table_name,
                separator=self.config.get("csv_separator", ";"),
                encoding=self.config.get("csv_encoding", "utf-8-sig"),
                chunk_size=self.config.get("csv_chunk_size", 50000),
                truncate_before_load=self.config.get("truncate_before_load", False),
                on_progress=load_progress,
            )
            load_result = loader.load()
            connector.disconnect()

            if not load_result.success:
                result.error = f"Chargement Oracle : {load_result.error}"
                return result

            ctx.extra["rows_loaded"] = load_result.rows_loaded
            ctx.log(
                f"Chargement Oracle : OK — {load_result.rows_loaded:,} lignes "
                f"en {load_result.duration_s:.1f}s ({load_result.chunks_count} chunks)"
            )
            result.success = True

        except Exception as e:
            result.error = str(e)

        return result
