"""
DataScheduler — core/steps/spark_sql.py
Étape : requête Spark SQL sur un cluster Hadoop via un nœud edge (SSH + Kerberos) — voir
core/spark.py pour le moteur d'exécution (connexion, kinit automatisé, exécution
non-interactive, rapatriement optionnel du résultat par SFTP). Ce step ne gère que la
résolution des 3 références (profil SSH, profil Kerberos, requête SQL), la mise en forme du
résultat récupéré et sa publication dans le contexte — toute la logique réseau/authentification
vit dans core/spark.py.
"""

import csv
import tempfile
from pathlib import Path

from .base import BaseStep, StepContext, StepResult

_QUOTING_MAP = {
    "QUOTE_MINIMAL":    csv.QUOTE_MINIMAL,
    "QUOTE_ALL":        csv.QUOTE_ALL,
    "QUOTE_NONNUMERIC": csv.QUOTE_NONNUMERIC,
    "QUOTE_NONE":       csv.QUOTE_NONE,
}


def _typed_for_quoting(field: str, quote_const: int):
    """Sous QUOTE_NONNUMERIC, le module csv ne laisse un champ non guillemeté que s'il reçoit un
    véritable int/float — la sortie brute de spark-sql n'étant que du texte (aucun typage
    préservé dans le fichier), on retente une conversion numérique champ par champ pour obtenir
    le même comportement que SqlExporter (core/sql_db.py, DB_EXTRACT) sur un vrai DataFrame typé."""
    if quote_const != csv.QUOTE_NONNUMERIC:
        return field
    try:
        return int(field)
    except ValueError:
        pass
    try:
        return float(field)
    except ValueError:
        return field


def _rewrite_as_csv(raw_path: Path, csv_path: Path, separator: str, encoding: str, quoting: str) -> None:
    """Reformate la sortie brute de spark-sql (tabulée, sans guillemets) selon le dialecte CSV
    demandé — mêmes options que SqlExporter pour DB_EXTRACT (séparateur/encodage/guillemets),
    où le CSV natif est fourni par pandas ; ici on le reconstruit nous-mêmes, spark-sql ne
    produisant qu'un texte tabulé brut. Traité en flux, ligne par ligne, jamais chargé
    intégralement en mémoire."""
    quote_const = _QUOTING_MAP.get(quoting, csv.QUOTE_MINIMAL)
    writer_kwargs = {"delimiter": separator, "quoting": quote_const}
    if quote_const == csv.QUOTE_NONE:
        writer_kwargs["escapechar"] = "\\"

    with open(raw_path, "r", encoding="utf-8", errors="replace", newline="") as src, \
         open(csv_path, "w", encoding=encoding, newline="") as dst:
        reader = csv.reader(src, delimiter="\t")
        writer = csv.writer(dst, **writer_kwargs)
        for row in reader:
            writer.writerow([_typed_for_quoting(f, quote_const) for f in row])


class SparkSqlStep(BaseStep):
    # PRODUCES volontairement vide, pas {"output_file"} : la production réelle dépend de
    # fetch_result (une valeur de config, pas connaissable statiquement par la classe) — même
    # raisonnement déjà appliqué à PythonScriptStep.PRODUCES (voir docs/COOKBOOK.md).
    # REQUIRES vide : l'étape est autonome, pilotée par ses 3 références, pas par ctx.output_file.

    def run(self, ctx: StepContext, on_progress=None) -> StepResult:
        result = StepResult()
        raw_path: Path | None = None
        csv_path: Path | None = None

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
                tmp = tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, prefix="ds_spark_raw_")
                raw_path = Path(tmp.name)
                tmp.close()

            ctx.log(f"Spark SQL : {edge_profile.host} — authentification Kerberos…")

            # run_spark_sql() connaît les phases réelles (connexion, kinit, requête, résultat) —
            # on_progress lui est transmis directement plutôt que de deviner l'étape ici
            # (chantier O : un seul tick avant/après ce bloc masquait de longues minutes de
            # requête en cours derrière un libellé figé "Authentification Kerberos…").
            spark_result = run_spark_sql(
                ssh_cfg, kerberos_cfg, spark_conf, query, fetch_result,
                local_output_path=raw_path, timeout=timeout, on_progress=on_progress,
            )

            if not spark_result.success:
                result.error = spark_result.error
                return result

            if fetch_result:
                if on_progress:
                    on_progress("Mise en forme du résultat…", 90)
                csv_tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, prefix="ds_spark_")
                csv_path = Path(csv_tmp.name)
                csv_tmp.close()
                _rewrite_as_csv(
                    raw_path, csv_path,
                    separator=self.config.get("csv_separator", ";"),
                    encoding=self.config.get("csv_encoding", "utf-8-sig"),
                    quoting=self.config.get("csv_quoting", "QUOTE_MINIMAL"),
                )
                ctx.output_file = csv_path
                output_name = self.config.get("output_name")
                if output_name:
                    ctx.artifacts[output_name] = csv_path
                ctx.log(f"Spark SQL : OK — résultat récupéré et mis en forme en {spark_result.duration_s:.1f}s")
            else:
                ctx.log(f"Spark SQL : OK — exécuté en {spark_result.duration_s:.1f}s")

            result.success = True

        except Exception as e:
            result.error = str(e)
        finally:
            # raw_path (sortie tabulée brute) n'est jamais l'artefact publié — toujours nettoyé,
            # succès ou non. csv_path (le vrai résultat mis en forme) suit la même règle que les
            # autres steps : nettoyé seulement en cas d'échec (sur succès il devient
            # ctx.output_file, nettoyé plus tard par run_pipeline()).
            if raw_path is not None and raw_path.exists():
                try:
                    raw_path.unlink()
                except OSError:
                    pass
            if csv_path is not None and not result.success and csv_path.exists():
                try:
                    csv_path.unlink()
                except OSError:
                    pass

        return result
