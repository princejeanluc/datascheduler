"""
DataScheduler — core/steps/spark_sql.py
Étape : requête Spark SQL sur un cluster Hadoop via un nœud edge (SSH + Kerberos) — voir
core/spark.py pour le moteur d'exécution (connexion, kinit automatisé, exécution
non-interactive, rapatriement optionnel du résultat par SFTP). Ce step ne gère que la
résolution des 3 références (profil SSH, profil Kerberos, requête SQL) et la publication du
résultat dans le contexte — toute la logique réseau/authentification vit dans core/spark.py.
"""

import tempfile
from pathlib import Path

from .base import BaseStep, StepContext, StepResult


class SparkSqlStep(BaseStep):
    # PRODUCES volontairement vide, pas {"output_file"} : la production réelle dépend de
    # fetch_result (une valeur de config, pas connaissable statiquement par la classe) — même
    # raisonnement déjà appliqué à PythonScriptStep.PRODUCES (voir docs/COOKBOOK.md).
    # REQUIRES vide : l'étape est autonome, pilotée par ses 3 références, pas par ctx.output_file.

    def run(self, ctx: StepContext, on_progress=None) -> StepResult:
        result = StepResult()
        tmp_path: Path | None = None

        def progress(msg: str, pct: int):
            if on_progress:
                on_progress(msg, pct)

        try:
            from database import db_manager as db
            from core.spark import config_from_profile, kerberos_config_from_profile, run_spark_sql

            edge_id      = self.config.get("edge_profile_id")
            kerberos_id  = self.config.get("kerberos_profile_id")
            query_id     = self.config.get("sql_query_id")
            fetch_result = bool(self.config.get("fetch_result", False))

            edge_profile     = db.get_ssh_profile(edge_id)
            kerberos_profile = db.get_kerberos_profile(kerberos_id)
            sql_query        = db.get_sql_query(query_id)

            if not edge_profile:
                result.error = f"Profil SSH ID {edge_id} introuvable."
                return result
            if not kerberos_profile:
                result.error = f"Profil Kerberos ID {kerberos_id} introuvable."
                return result
            if not sql_query:
                result.error = f"Requête SQL ID {query_id} introuvable."
                return result

            ssh_cfg      = config_from_profile(edge_profile)
            kerberos_cfg = kerberos_config_from_profile(kerberos_profile)
            spark_conf   = ctx.resolve_tokens(self.config.get("spark_conf", ""))
            query        = ctx.resolve_tokens(sql_query.sql_text)
            timeout      = int(self.config.get("timeout", 3600))

            if fetch_result:
                tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, prefix="ds_")
                tmp_path = Path(tmp.name)
                tmp.close()

            ctx.log(f"Spark SQL : {edge_profile.host} — authentification Kerberos…")
            progress("Authentification Kerberos…", 20)

            spark_result = run_spark_sql(
                ssh_cfg, kerberos_cfg, spark_conf, query, fetch_result,
                local_output_path=tmp_path, timeout=timeout,
            )
            progress("Exécution de la requête…", 70)

            if not spark_result.success:
                result.error = spark_result.error
                return result

            if fetch_result:
                ctx.output_file = tmp_path
                output_name = self.config.get("output_name")
                if output_name:
                    ctx.artifacts[output_name] = tmp_path
                ctx.log(f"Spark SQL : OK — résultat récupéré en {spark_result.duration_s:.1f}s")
            else:
                ctx.log(f"Spark SQL : OK — exécuté en {spark_result.duration_s:.1f}s")

            result.success = True

        except Exception as e:
            result.error = str(e)
        finally:
            # run_spark_sql() gère déjà son propre nettoyage réseau/fichiers distants ; ce step
            # ne nettoie que son fichier local temporaire, en cas d'échec (même principe que
            # db_extract.py : sur succès, le fichier devient ctx.output_file, nettoyé plus tard
            # par run_pipeline()).
            if tmp_path is not None and not result.success and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

        return result
