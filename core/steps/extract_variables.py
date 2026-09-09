"""
DataScheduler — core/steps/extract_variables.py
Étape : lit un fichier source déjà produit (CSV) attendu à UNE seule ligne de données (ex :
résultat d'agrégation SQL — MAX(date), SUM(montant)...), et publie certaines de ses colonnes
sous des noms de variable dans ctx.variables (chantier EXTRACT_VARIABLES).

Responsabilité volontairement étroite : cette étape n'exécute AUCUNE requête elle-même — elle
consomme un fichier au même titre que LOCAL_COPY/DB_LOAD (explicit_path ou ctx.output_file), la
requête qui a produit ce fichier reste l'affaire de l'étape en amont (DB_EXTRACT). Ne modifie
jamais ctx.output_file : un fichier lu ici reste sélectionnable en aval sous la clé de l'étape
qui l'a réellement produit.
"""

import csv
from datetime import datetime
from pathlib import Path

from core.date_tokens import translate_date_format
from .base import BaseStep, StepContext, StepResult

# Format de sortie ISO-8601 pour les valeurs Date/Date-heure — voir StepContext.variables :
# l'ordre lexicographique d'une chaîne ISO coïncide avec l'ordre chronologique, donc CONDITION
# (core/steps/condition.py) peut comparer deux var: de type date avec les opérateurs de chaîne
# déjà écrits, sans branche de type supplémentaire ni objet date/datetime Python à transporter.
_ISO_DATE     = "%Y-%m-%d"
_ISO_DATETIME = "%Y-%m-%dT%H:%M:%S"


def _coerce(raw: str, type_: str, date_format: str, source: str) -> str | int | float:
    """Convertit la valeur texte brute d'une cellule CSV selon le type demandé pour cette
    correspondance. Lève ValueError (message déjà destiné à l'utilisateur final) en cas
    d'échec — jamais de valeur silencieusement approximée."""
    if type_ == "number":
        try:
            return float(raw) if "." in raw else int(raw)
        except ValueError:
            raise ValueError(f"Colonne « {source} » : valeur {raw!r} n'est pas un nombre valide.")
    if type_ in ("date", "datetime"):
        if not date_format:
            raise ValueError(f"Colonne « {source} » : format de date manquant pour cette correspondance.")
        strptime_fmt = translate_date_format(date_format)
        try:
            parsed = datetime.strptime(raw, strptime_fmt)
        except ValueError:
            raise ValueError(
                f"Colonne « {source} » : valeur {raw!r} ne correspond pas au format {date_format!r}."
            )
        return parsed.strftime(_ISO_DATETIME if type_ == "datetime" else _ISO_DATE)
    return raw   # "text" (défaut) — valeur brute, sans coercition


class ExtractVariablesStep(BaseStep):
    REQUIRES = {"output_file"}

    def run(self, ctx: StepContext, cancel_event=None, on_progress=None) -> StepResult:
        result = StepResult()

        try:
            explicit_path = (self.config.get("explicit_path") or "").strip()
            source_path = Path(ctx.resolve_tokens(explicit_path)) if explicit_path else ctx.output_file
            if not source_path or not source_path.exists():
                result.error = "Aucun fichier source disponible (ni chemin explicite, ni contexte)."
                return result

            mappings = self.config.get("mappings") or []
            if not mappings:
                result.error = "Aucune correspondance configurée."
                return result

            separator = self.config.get("csv_separator", ";")
            encoding  = self.config.get("csv_encoding", "utf-8-sig")

            with open(source_path, "r", encoding=encoding, newline="") as f:
                rows = list(csv.DictReader(f, delimiter=separator))

            if len(rows) == 0:
                result.error = "Aucune ligne de données dans la source (une seule attendue)."
                return result
            if len(rows) > 1:
                result.error = (
                    f"{len(rows)} lignes trouvées dans la source, une seule attendue — utilisez "
                    "une requête d'agrégation en amont pour ne produire qu'une ligne."
                )
                return result

            row = rows[0]
            extracted: dict = {}
            for mapping in mappings:
                source = (mapping.get("source") or "").strip()
                target = (mapping.get("target") or "").strip()
                if not source or not target:
                    result.error = "Correspondance incomplète (colonne source et variable cible requises)."
                    return result
                if source not in row:
                    available = ", ".join(row.keys())
                    result.error = f"Colonne « {source} » absente de la source (colonnes disponibles : {available})."
                    return result
                extracted[target] = _coerce(
                    row[source], mapping.get("type", "text"), mapping.get("date_format", ""), source
                )

            ctx.variables.update(extracted)
            ctx.log(f"Variables extraites : {', '.join(extracted.keys())}")
            result.success = True

        except Exception as e:
            result.error = str(e)

        return result
