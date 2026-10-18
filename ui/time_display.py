"""
DataScheduler — ui/time_display.py
Conversion et formatage partagés des heures affichées (refonte, lot 0b — FONDATIONS.md section
4). La base stocke les instants en UTC naïf (`datetime.utcnow()`), sauf `Pipeline.next_run_at`
(et sa copie `expected_at` dans les dialogues de rattrapage), stocké naïf dans le fuseau réglé
(`AppSettings.timezone`) — voir `core/missed_runs.py`. Le fuseau est relu à chaque appel via
`db.get_app_settings()` plutôt que mis en cache : plus simple, aucun risque d'oubli
d'invalidation au moment où l'utilisateur change de fuseau dans les Paramètres.

`fmt` reste un paramètre optionnel sur chaque fonction de formatage (pas dans l'esquisse de
FONDATIONS.md) : il permet de migrer chaque site d'affichage existant vers la conversion
partagée sans changer la précision qu'il affichait déjà (le code actuel mélange par endroits
"%H:%M:%S" et "%H:%M", "%d/%m/%Y %H:%M:%S" et "%d/%m/%Y %H:%M" selon l'écran — centraliser la
conversion n'est pas l'occasion de les uniformiser sans que la fiche le demande, REGLES.md
section 1). Voir docs/refonte/impact/0b.md.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from database import db_manager as db

_UTC = ZoneInfo("UTC")


def _configured_zone() -> ZoneInfo:
    return ZoneInfo(db.get_app_settings().timezone)


def to_display(dt_utc: datetime) -> datetime:
    """Instant UTC naïf → naïf dans le fuseau réglé, prêt à formater."""
    return dt_utc.replace(tzinfo=_UTC).astimezone(_configured_zone()).replace(tzinfo=None)


def fmt_time(dt_utc: datetime | None, fmt: str = "%H:%M:%S") -> str:
    return to_display(dt_utc).strftime(fmt) if dt_utc else "—"


def fmt_datetime(dt_utc: datetime | None, fmt: str = "%d/%m/%Y %H:%M") -> str:
    return to_display(dt_utc).strftime(fmt) if dt_utc else "—"


def fmt_time_local(dt: datetime | None, fmt: str = "%H:%M") -> str:
    """Variante non convertissante — pour Pipeline.next_run_at et expected_at, déjà dans le
    fuseau réglé."""
    return dt.strftime(fmt) if dt else "—"


def fmt_datetime_local(dt: datetime | None, fmt: str = "%d/%m/%Y %H:%M") -> str:
    return dt.strftime(fmt) if dt else "—"


def fmt_relative(dt_utc: datetime | None) -> str:
    """« il y a 45s » / « il y a 4 min » / « il y a 2 h » / « il y a 3 jours » — généralisation
    des deux idiomes dupliqués qu'il remplace (settings_view.py en secondes, connections_view.py
    en jours), dont la sortie reste identique dans leurs plages respectives."""
    if not dt_utc:
        return "—"
    seconds = int((datetime.utcnow() - dt_utc).total_seconds())
    if seconds < 60:
        return f"il y a {seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"il y a {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"il y a {hours} h"
    days = hours // 24
    return f"il y a {days} jour{'s' if days > 1 else ''}"
