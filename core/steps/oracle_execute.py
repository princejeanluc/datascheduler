"""
DataScheduler — core/steps/oracle_execute.py
Étape : connexion Oracle, exécution d'une instruction SQL/PLSQL (DML/DDL/procédure/
bloc anonyme) sans extraction — pas de fichier produit.
"""

from .base import BaseStep, StepContext, StepResult


class OracleExecuteStep(BaseStep):

    def run(self, ctx: StepContext, on_progress=None) -> StepResult:
        result = StepResult()

        def progress(msg: str, pct: int):
            if on_progress:
                on_progress(msg, pct)

        try:
            from database import db_manager as db
            from core.oracle import OracleConnector, config_from_profile

            oracle_id = self.config.get("oracle_profile_id")
            query_id  = self.config.get("sql_query_id")
            commit    = self.config.get("commit", True)

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

            sql_text = ctx.resolve_tokens(sql_query.sql_text)

            progress("Exécution SQL…", 50)
            cursor = connector.connection.cursor()
            cursor.execute(sql_text)
            rows_affected = cursor.rowcount
            ctx.extra["rows_affected"] = rows_affected
            ctx.log(f"Exécution SQL : OK — {rows_affected} ligne(s) affectée(s)")

            if commit:
                connector.connection.commit()
                ctx.log("Commit effectué.")
            else:
                ctx.log("Commit désactivé (commit=False) — connexion fermée sans valider.")

            connector.disconnect()
            result.success = True

        except Exception as e:
            result.error = str(e)

        return result
