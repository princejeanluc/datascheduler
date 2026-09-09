"""
DataScheduler — core/date_tokens.py
Vocabulaire de tokens de date partagé ({dd}/{MM}/{yyyy}...) — un seul mapping vers les
directives strftime/strptime de Python. Introduit avec `csv_date_format` (DB_EXTRACT) pour
FORMATER une date, réutilisé tel quel par EXTRACT_VARIABLES pour PARSER une date — les mêmes
directives (%d, %m, %Y...) servent aux deux usages, seule la fonction stdlib appelée diffère
(strftime vs strptime). Un seul endroit à faire évoluer si le vocabulaire de tokens change.
"""

_DATE_FORMAT_TOKEN_MAP = {
    "{yyyy}": "%Y", "{yy}": "%y", "{MM}": "%m", "{dd}": "%d",
    "{HH}": "%H", "{mm}": "%M", "{ss}": "%S",
}


def translate_date_format(template: str) -> str:
    """Traduit un format écrit avec les tokens habituels de l'appli (ex: "{dd}/{MM}/{yyyy}") en
    directive strftime/strptime (ex: "%d/%m/%Y"). Un token non reconnu est laissé tel quel —
    apparaîtra littéralement dans le résultat, un échec visible plutôt qu'un plantage."""
    result = template
    for token, directive in _DATE_FORMAT_TOKEN_MAP.items():
        result = result.replace(token, directive)
    return result
