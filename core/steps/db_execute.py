"""
DataScheduler — core/steps/db_execute.py
Étape : connexion à une base (tout moteur), exécution d'une instruction SQL/PLSQL
(DML/DDL/procédure/bloc anonyme) sans extraction — pas de fichier produit.
"""

from sqlalchemy import text

from .base import BaseStep, StepContext, StepResult


class DbExecuteStep(BaseStep):

    def run(self, ctx: StepContext, on_progress=None) -> StepResult:
        result = StepResult()

        def progress(msg: str, pct: int):
            if on_progress:
                on_progress(msg, pct)

        try:
            from database import db_manager as db
            from core.sql_db import SqlConnector, config_from_profile, get_profile_object, is_plsql_block

            db_type    = self.config.get("db_type", "ORACLE")
            profile_id = self.config.get("profile_id")
            query_id   = self.config.get("sql_query_id")
            commit     = self.config.get("commit", True)

            profile   = get_profile_object(db_type, profile_id)
            sql_query = db.get_sql_query(query_id)

            if not profile:
                result.error = f"Profil {db_type} ID {profile_id} introuvable."
                return result
            if not sql_query:
                result.error = f"Requête SQL ID {query_id} introuvable."
                return result

            ctx.log(f"Connexion {db_type} : {profile.host}:{profile.port}")
            progress("Connexion…", 10)

            cfg       = config_from_profile(db_type, profile)
            connector = SqlConnector(cfg)
            connector.connect()
            ctx.log(f"Connexion {db_type} : OK")

            sql_text = ctx.resolve_tokens(sql_query.sql_text)

            progress("Exécution SQL…", 50)
            cursor_result = connector.connection.execute(text(sql_text))

            # La détection de bloc PL/SQL n'a de sens que pour Oracle — pour les autres
            # moteurs (appel de procédure MySQL, bloc DO $$ ... $$ PostgreSQL...), le
            # rowcount peut tout autant ne pas refléter le DML interne, mais on ne tente
            # pas de détecter chaque syntaxe spécifique (hors scope tant qu'un besoin réel
            # ne le justifie pas) — juste un avertissement générique.
            if db_type == "ORACLE" and is_plsql_block(sql_text):
                ctx.extra["rows_affected"] = None
                ctx.log(
                    "Exécution SQL : OK — bloc PL/SQL. Le nombre de lignes affectées par une "
                    "instruction DML exécutée à l'intérieur du bloc (ex : via une procédure "
                    "stockée) n'est pas remonté par le pilote Oracle ; vérifiez le résultat "
                    "directement en base."
                )
            else:
                rows_affected = cursor_result.rowcount
                ctx.extra["rows_affected"] = rows_affected
                ctx.log(f"Exécution SQL : OK — {rows_affected} ligne(s) affectée(s)")
                if db_type != "ORACLE":
                    ctx.log(
                        "Note : si cette instruction appelle une procédure stockée, ce "
                        "rowcount peut ne pas refléter les lignes affectées à l'intérieur."
                    )

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
