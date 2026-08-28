"""
DataScheduler — core/steps/db_extract.py
Étape : connexion à une base (Oracle, MySQL, PostgreSQL, SQL Server), exécution SQL,
export CSV vers fichier temporaire.
"""

import tempfile
from pathlib import Path

from .base import BaseStep, StepContext, StepResult

# {yyyy}/{MM}/{dd}... sont déjà le vocabulaire de tokens utilisé partout ailleurs dans l'appli
# (chemins FTP, noms de fichiers, sujets d'email — voir StepContext.resolve_tokens) — plutôt que
# d'exposer la syntaxe strftime brute de pandas à l'utilisateur pour ce champ, on traduit dans
# le même vocabulaire déjà connu. Mapping volontairement 1:1, aucune ambiguïté entre tokens
# (chacun est encadré par ses propres accolades).
_DATE_FORMAT_TOKEN_MAP = {
    "{yyyy}": "%Y", "{yy}": "%y", "{MM}": "%m", "{dd}": "%d",
    "{HH}": "%H", "{mm}": "%M", "{ss}": "%S",
}


def _translate_date_format(template: str) -> str:
    """Traduit un format écrit avec les tokens habituels de l'appli (ex: "{dd}/{MM}/{yyyy}")
    en directive strftime (ex: "%d/%m/%Y"), seule syntaxe comprise par pandas.to_csv(). Un
    token non reconnu est laissé tel quel — apparaîtra littéralement dans le CSV produit,
    un échec visible plutôt qu'un plantage."""
    result = template
    for token, directive in _DATE_FORMAT_TOKEN_MAP.items():
        result = result.replace(token, directive)
    return result


class DbExtractStep(BaseStep):
    PRODUCES = {"output_file"}

    def run(self, ctx: StepContext, cancel_event=None, on_progress=None) -> StepResult:
        result = StepResult()
        connector = None
        tmp_path: Path | None = None

        def progress(msg: str, pct: int):
            if on_progress:
                on_progress(msg, pct)

        try:
            from database import db_manager as db
            from core.sql_db import SqlConnector, SqlExporter, config_from_profile, get_profile_object

            db_type    = self.config.get("db_type", "ORACLE")
            profile_id = self.config.get("profile_id")
            query_id   = self.config.get("sql_query_id")

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

            tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, prefix="ds_")
            tmp_path = Path(tmp.name)
            tmp.close()

            rows_done = [0]

            def export_progress(rows: int, chunk_idx: int):
                rows_done[0] = rows
                progress(f"Export… {rows:,} lignes", min(25 + chunk_idx * 2, 75))

            date_format_tpl = self.config.get("csv_date_format") or ""
            exporter = SqlExporter(
                connector=connector,
                sql=ctx.resolve_tokens(sql_query.sql_text),
                output_path=tmp_path,
                separator=self.config.get("csv_separator",  ";"),
                encoding=self.config.get("csv_encoding",    "utf-8-sig"),
                chunk_size=self.config.get("csv_chunk_size", 50000),
                quoting=self.config.get("csv_quoting",      "QUOTE_NONNUMERIC"),
                date_format=_translate_date_format(date_format_tpl) if date_format_tpl else None,
                on_progress=export_progress,
                cancel_event=cancel_event,
            )
            export_result = exporter.export()

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
        finally:
            # try/finally plutôt qu'un disconnect() en fin de bloc try : garantit la fermeture
            # de la connexion même si exporter.export() lève (pas seulement quand elle renvoie
            # un résultat en échec) — sans ça, une exception en cours d'export laissait la
            # session DB ouverte côté serveur.
            if connector is not None:
                try:
                    connector.disconnect()
                except Exception:
                    pass
            # Le fichier temporaire est créé avant de savoir si l'export va réussir ; s'il
            # échoue (résultat en échec ou exception), il ne sera jamais référencé dans
            # ctx.artifacts donc jamais nettoyé par run_pipeline — à nettoyer ici.
            if tmp_path is not None and not result.success and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

        return result
