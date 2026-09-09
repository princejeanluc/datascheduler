"""
DataScheduler — core/steps/sqoop_import.py
Étape : import d'une table Oracle vers Hive/HCatalog via Sqoop, sur un cluster Hadoop via un
nœud edge — miroir de sqoop_export.py dans l'autre sens (voir core/sqoop.py pour le moteur
d'exécution partagé, core.sqoop._run_sqoop). Ce step ne gère que la résolution des références
(profil SSH obligatoire ; profil Kerberos et profil d'élévation — sudo su — tous deux
optionnels) et des jetons dans les champs de table — toute la logique réseau/authentification/
commande vit dans core/sqoop.py.

Suppose la table Hive/HCatalog cible déjà créée (même choix que DB_LOAD, jamais de génération
de DDL). `num_mappers` défaut à 1 (aucune configuration supplémentaire requise, fonctionne pour
n'importe quelle table) ; au-delà, `split_by_column` devient obligatoire — Sqoop ne peut pas
paralléliser la lecture Oracle sans elle.

Étape autonome, comme SqoopExportStep : ni REQUIRES ni PRODUCES, ne touche jamais ctx.output_file
(sqoop import écrit dans Hive, ne produit aucun fichier local à publier dans le contexte).
"""

from .base import BaseStep, StepContext, StepResult


class SqoopImportStep(BaseStep):

    def run(self, ctx: StepContext, cancel_event=None, on_progress=None) -> StepResult:
        result = StepResult()

        try:
            from database import db_manager as db
            from core.hadoop_edge import (
                config_from_profile, kerberos_config_from_profile, config_from_elevation_profile,
            )
            from core.sql_db import config_from_profile as oracle_config_from_profile
            from core.sqoop import build_oracle_jdbc_url, build_sqoop_import_command, run_sqoop_import

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

            oracle_table      = ctx.resolve_tokens(self.config.get("oracle_table", ""))
            hcatalog_database = ctx.resolve_tokens(self.config.get("hcatalog_database", ""))
            hcatalog_table    = ctx.resolve_tokens(self.config.get("hcatalog_table", ""))
            sqoop_conf        = ctx.resolve_tokens(self.config.get("sqoop_conf", ""))
            num_mappers       = int(self.config.get("num_mappers") or 1)
            split_by_column   = ctx.resolve_tokens(self.config.get("split_by_column", ""))

            if num_mappers > 1 and not split_by_column:
                result.error = (
                    "Colonne de partitionnement (« split-by ») requise dès que le nombre de "
                    "mappers dépasse 1 — Sqoop ne peut pas paralléliser la lecture sans elle."
                )
                return result

            # Journalisation avec mot de passe masqué — jamais la commande réelle, pour ne
            # jamais faire fuiter le mot de passe Oracle en clair dans PipelineRun.log_text.
            masked_cmd = build_sqoop_import_command(
                build_oracle_jdbc_url(oracle_cfg), oracle_cfg.username, oracle_cfg.password,
                oracle_table, hcatalog_database, hcatalog_table, num_mappers, split_by_column,
                sqoop_conf, masked=True,
            )
            steps_desc = []
            if elevation_cfg:
                steps_desc.append(f"élévation vers « {elevation_cfg.target_user} »")
            if krb_cfg:
                steps_desc.append("authentification Kerberos")
            ctx.log(f"Sqoop import : {edge_profile.host}" + (f" — {', '.join(steps_desc)}…" if steps_desc else ""))
            ctx.log(f"Sqoop import : {masked_cmd}")

            sqoop_result = run_sqoop_import(
                ssh_cfg, krb_cfg, oracle_cfg,
                oracle_table, hcatalog_database, hcatalog_table, num_mappers, split_by_column,
                sqoop_conf,
                elevation_cfg=elevation_cfg, on_progress=on_progress,
                cancel_event=cancel_event,
            )

            if not sqoop_result.success:
                result.error = sqoop_result.error
                return result

            ctx.log(f"Sqoop import : OK — exécuté en {sqoop_result.duration_s:.1f}s")
            result.success = True

        except Exception as e:
            result.error = str(e)

        return result
