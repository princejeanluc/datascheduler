"""
DataScheduler — core/steps/sqoop_export.py
Étape : export d'une table Hive/HCatalog vers Oracle via Sqoop, sur un cluster Hadoop via un
nœud edge — voir core/sqoop.py pour le moteur d'exécution (connexion, élévation/kinit
automatisés, commande sqoop, nettoyage). Ce step ne gère que la résolution des références
(profil SSH obligatoire ; profil Kerberos et profil d'élévation — sudo su — tous deux
optionnels, certaines équipes n'utilisant ni l'un ni l'autre, ou l'un sans l'autre) et des
jetons dans les champs de table — toute la logique réseau/authentification/commande vit dans
core/sqoop.py.

Étape autonome, comme DB_EXECUTE : ni REQUIRES ni PRODUCES, ne touche jamais ctx.output_file
(sqoop export écrit dans Oracle, ne produit aucun fichier local à publier dans le contexte).
"""

from .base import BaseStep, StepContext, StepResult


class SqoopExportStep(BaseStep):

    def run(self, ctx: StepContext, on_progress=None) -> StepResult:
        result = StepResult()

        def progress(msg: str, pct: int):
            if on_progress:
                on_progress(msg, pct)

        try:
            from database import db_manager as db
            from core.hadoop_edge import (
                config_from_profile, kerberos_config_from_profile, config_from_elevation_profile,
            )
            from core.sql_db import config_from_profile as oracle_config_from_profile
            from core.sqoop import build_sqoop_export_command, build_oracle_jdbc_url, run_sqoop_export

            edge_id      = self.config.get("edge_profile_id")
            kerberos_id  = self.config.get("kerberos_profile_id")
            elevation_id = self.config.get("elevation_profile_id")
            oracle_id    = self.config.get("oracle_profile_id")

            edge_profile   = db.get_ssh_profile(edge_id)
            oracle_profile = db.get_oracle_profile(oracle_id)

            if not edge_profile:
                result.error = f"Profil SSH ID {edge_id} introuvable."
                return result
            if not oracle_profile:
                result.error = f"Profil Oracle ID {oracle_id} introuvable."
                return result

            krb_cfg = None
            if kerberos_id:
                kerberos_profile = db.get_kerberos_profile(kerberos_id)
                if not kerberos_profile:
                    result.error = f"Profil Kerberos ID {kerberos_id} introuvable."
                    return result
                krb_cfg = kerberos_config_from_profile(kerberos_profile)

            elevation_cfg = None
            if elevation_id:
                elevation_profile = db.get_elevation_profile(elevation_id)
                if not elevation_profile:
                    result.error = f"Profil d'élévation ID {elevation_id} introuvable."
                    return result
                elevation_cfg = config_from_elevation_profile(elevation_profile)

            ssh_cfg    = config_from_profile(edge_profile)
            oracle_cfg = oracle_config_from_profile("ORACLE", oracle_profile)

            hcatalog_database = ctx.resolve_tokens(self.config.get("hcatalog_database", ""))
            hcatalog_table    = ctx.resolve_tokens(self.config.get("hcatalog_table", ""))
            oracle_table      = ctx.resolve_tokens(self.config.get("oracle_table", ""))
            sqoop_conf        = ctx.resolve_tokens(self.config.get("sqoop_conf", ""))

            # Journalisation avec mot de passe masqué — jamais la commande réelle, pour ne
            # jamais faire fuiter le mot de passe Oracle en clair dans PipelineRun.log_text.
            masked_cmd = build_sqoop_export_command(
                build_oracle_jdbc_url(oracle_cfg), oracle_cfg.username, oracle_cfg.password,
                hcatalog_database, hcatalog_table, oracle_table, sqoop_conf, masked=True,
            )
            steps_desc = []
            if elevation_cfg:
                steps_desc.append(f"élévation vers « {elevation_cfg.target_user} »")
            if krb_cfg:
                steps_desc.append("authentification Kerberos")
            ctx.log(f"Sqoop export : {edge_profile.host}" + (f" — {', '.join(steps_desc)}…" if steps_desc else ""))
            ctx.log(f"Sqoop export : {masked_cmd}")
            progress("Connexion…", 20)

            sqoop_result = run_sqoop_export(
                ssh_cfg, krb_cfg, oracle_cfg,
                hcatalog_database, hcatalog_table, oracle_table, sqoop_conf,
                elevation_cfg=elevation_cfg,
            )
            progress("Export Sqoop…", 80)

            if not sqoop_result.success:
                result.error = sqoop_result.error
                return result

            ctx.log(f"Sqoop export : OK — exécuté en {sqoop_result.duration_s:.1f}s")
            result.success = True

        except Exception as e:
            result.error = str(e)

        return result
