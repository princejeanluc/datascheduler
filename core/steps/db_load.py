"""
DataScheduler — core/steps/db_load.py
Étape : chargement du fichier de contexte (CSV) vers une table (tout moteur),
association simple par en-tête CSV.
"""

from .base import BaseStep, StepContext, StepResult


class DbLoadStep(BaseStep):
    REQUIRES = {"output_file"}

    def run(self, ctx: StepContext, on_progress=None) -> StepResult:
        result = StepResult()

        def progress(msg: str, pct: int):
            if on_progress:
                on_progress(msg, pct)

        try:
            from core.sql_db import SqlConnector, SqlLoader, config_from_profile, get_profile_object

            if not ctx.output_file or not ctx.output_file.exists():
                result.error = "Aucun fichier source disponible dans le contexte."
                return result

            db_type    = self.config.get("db_type", "ORACLE")
            profile_id = self.config.get("profile_id")
            table_name = self.config.get("table_name", "")

            profile = get_profile_object(db_type, profile_id)
            if not profile:
                result.error = f"Profil {db_type} ID {profile_id} introuvable."
                return result
            if not table_name:
                result.error = "Table cible non configurée."
                return result

            ctx.log(f"Connexion {db_type} : {profile.host}:{profile.port}")
            progress("Connexion…", 10)

            cfg       = config_from_profile(db_type, profile)
            connector = SqlConnector(cfg)
            connector.connect()
            ctx.log(f"Connexion {db_type} : OK")

            rows_done = [0]

            def load_progress(rows: int, chunk_idx: int):
                rows_done[0] = rows
                progress(f"Chargement… {rows:,} lignes", min(25 + chunk_idx * 2, 90))

            loader = SqlLoader(
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
                result.error = f"Chargement : {load_result.error}"
                return result

            ctx.extra["rows_loaded"] = load_result.rows_loaded
            ctx.log(
                f"Chargement : OK — {load_result.rows_loaded:,} lignes "
                f"en {load_result.duration_s:.1f}s ({load_result.chunks_count} chunks)"
            )
            result.success = True

        except Exception as e:
            result.error = str(e)

        return result
