"""
DataScheduler — tests/test_time_display.py
Refonte, lot 0b : conversion et formatage partagés des heures affichées (ui/time_display.py).
"""

from datetime import datetime, timedelta

from database import db_manager as db
from ui.time_display import (
    to_display, fmt_time, fmt_datetime, fmt_time_local, fmt_datetime_local, fmt_relative,
)


def test_run_at_05_utc_displays_as_07_with_europe_paris_in_summer(test_db):
    """Critère d'acceptation explicite de FONDATIONS.md section 4."""
    db.update_app_settings(timezone="Europe/Paris")
    dt_utc = datetime(2026, 7, 14, 5, 0, 0)   # été — CEST = UTC+2
    assert to_display(dt_utc) == datetime(2026, 7, 14, 7, 0, 0)
    assert fmt_time(dt_utc) == "07:00:00"
    assert fmt_datetime(dt_utc) == "14/07/2026 07:00"


def test_conversion_respects_winter_offset(test_db):
    db.update_app_settings(timezone="Europe/Paris")
    dt_utc = datetime(2026, 1, 14, 5, 0, 0)   # hiver — CET = UTC+1
    assert to_display(dt_utc) == datetime(2026, 1, 14, 6, 0, 0)


def test_no_conversion_when_timezone_is_utc(test_db):
    db.update_app_settings(timezone="UTC")
    dt_utc = datetime(2026, 7, 14, 5, 0, 0)
    assert to_display(dt_utc) == dt_utc


def test_fmt_time_accepts_a_custom_format(test_db):
    db.update_app_settings(timezone="UTC")
    assert fmt_time(datetime(2026, 1, 1, 9, 5, 0), fmt="%H:%M") == "09:05"


def test_fmt_datetime_accepts_a_custom_format(test_db):
    db.update_app_settings(timezone="UTC")
    assert fmt_datetime(datetime(2026, 1, 1, 9, 5, 0), fmt="%d/%m %H:%M") == "01/01 09:05"


def test_fmt_time_and_fmt_datetime_return_dash_for_none(test_db):
    db.update_app_settings(timezone="UTC")
    assert fmt_time(None) == "—"
    assert fmt_datetime(None) == "—"


def test_fmt_local_variants_do_not_convert(test_db):
    """next_run_at est déjà dans le fuseau réglé — fmt_time_local/fmt_datetime_local ne doivent
    jamais appliquer de second décalage, même si le fuseau réglé n'est pas UTC."""
    db.update_app_settings(timezone="Asia/Tokyo")
    dt_local = datetime(2026, 7, 14, 9, 30, 0)
    assert fmt_time_local(dt_local) == "09:30"
    assert fmt_datetime_local(dt_local) == "14/07/2026 09:30"


def test_fmt_local_variants_accept_a_custom_format_and_dash_for_none(test_db):
    assert fmt_datetime_local(datetime(2026, 1, 1, 9, 5), fmt="%d/%m %H:%M") == "01/01 09:05"
    assert fmt_time_local(None) == "—"
    assert fmt_datetime_local(None) == "—"


# ──────────────────────────────────────────────
#  fmt_relative — reproduit exactement le texte des deux idiomes dupliqués qu'il remplace
# ──────────────────────────────────────────────

def test_fmt_relative_seconds_matches_settings_view_wording(test_db):
    """settings_view.py affichait f"... il y a {int(age_s)}s" — même texte attendu."""
    dt_utc = datetime.utcnow() - timedelta(seconds=45)
    assert fmt_relative(dt_utc) == "il y a 45s"


def test_fmt_relative_minutes():
    dt_utc = datetime.utcnow() - timedelta(minutes=4)
    assert fmt_relative(dt_utc) == "il y a 4 min"


def test_fmt_relative_hours():
    dt_utc = datetime.utcnow() - timedelta(hours=2)
    assert fmt_relative(dt_utc) == "il y a 2 h"


def test_fmt_relative_days_matches_connections_view_wording():
    """connections_view.py affichait f"Testé il y a {age_days} jour{'s' if age_days > 1 else ''}"
    — même pluriel attendu."""
    dt_utc = datetime.utcnow() - timedelta(days=1, hours=1)
    assert fmt_relative(dt_utc) == "il y a 1 jour"

    dt_utc = datetime.utcnow() - timedelta(days=3, hours=1)
    assert fmt_relative(dt_utc) == "il y a 3 jours"


def test_fmt_relative_returns_dash_for_none():
    assert fmt_relative(None) == "—"
