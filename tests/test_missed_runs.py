"""
DataScheduler — tests/test_missed_runs.py
Détection des pipelines manqués au démarrage (chantier rattrapage) : core/missed_runs.py.
"""

from datetime import datetime, timedelta

from database import db_manager as db
from database.models import Pipeline
from core.missed_runs import detect_missed_runs, get_pending, resolve


def _set_next_run_at(pipeline_id: int, when) -> None:
    with db.get_session() as s:
        obj = s.get(Pipeline, pipeline_id)
        obj.next_run_at = when


def _settings(timezone="UTC", misfire_grace_time_min=60):
    db.update_app_settings(timezone=timezone, misfire_grace_time_min=misfire_grace_time_min)
    return db.get_app_settings()


def test_detects_a_pipeline_missed_within_tolerance(test_db):
    p = db.create_pipeline(name="missed-in-tolerance")
    _set_next_run_at(p.id, datetime.utcnow() - timedelta(minutes=30))
    settings = _settings(timezone="UTC", misfire_grace_time_min=60)

    missed = detect_missed_runs(settings)

    assert [m["pipeline_id"] for m in missed] == [p.id]
    assert missed[0]["name"] == "missed-in-tolerance"
    assert missed[0]["late_minutes"] in (29, 30)   # marge d'exécution du test


def test_excludes_pipeline_whose_next_run_is_in_the_future(test_db):
    p = db.create_pipeline(name="future-run")
    _set_next_run_at(p.id, datetime.utcnow() + timedelta(hours=1))
    settings = _settings()

    assert detect_missed_runs(settings) == []


def test_excludes_pipeline_with_no_next_run_at(test_db):
    db.create_pipeline(name="never-scheduled")   # next_run_at reste None par défaut
    settings = _settings()

    assert detect_missed_runs(settings) == []


def test_excludes_miss_beyond_tolerance(test_db):
    """Trop ancien pour être proposé — comme aujourd'hui implicitement au-delà de
    misfire_grace_time_min, jamais rattrapé."""
    p = db.create_pipeline(name="too-stale")
    _set_next_run_at(p.id, datetime.utcnow() - timedelta(hours=3))
    settings = _settings(misfire_grace_time_min=60)

    assert detect_missed_runs(settings) == []


def test_excludes_inactive_pipeline(test_db):
    p = db.create_pipeline(name="inactive-missed")
    db.set_pipeline_active(p.id, False)
    _set_next_run_at(p.id, datetime.utcnow() - timedelta(minutes=10))
    settings = _settings()

    assert detect_missed_runs(settings) == []


def test_respects_configured_timezone_not_utc(test_db):
    """next_run_at est une heure murale dans le fuseau configuré de l'app, pas UTC — un
    fuseau très décalé (UTC+9, Tokyo) ne doit jamais faire passer un pipeline réellement futur
    (dans SON fuseau) pour manqué juste parce que UTC est déjà plus tard."""
    p = db.create_pipeline(name="tokyo-future")
    from zoneinfo import ZoneInfo
    # "Maintenant" à Tokyo, plus 30 minutes -> toujours dans le futur dans SON propre fuseau.
    now_tokyo = datetime.now(ZoneInfo("Asia/Tokyo")).replace(tzinfo=None)
    _set_next_run_at(p.id, now_tokyo + timedelta(minutes=30))
    settings = _settings(timezone="Asia/Tokyo")

    assert detect_missed_runs(settings) == []


def test_get_pending_reflects_last_detection(test_db):
    p = db.create_pipeline(name="pending-reflect")
    _set_next_run_at(p.id, datetime.utcnow() - timedelta(minutes=5))
    settings = _settings()

    detect_missed_runs(settings)

    assert [m["pipeline_id"] for m in get_pending()] == [p.id]


def test_resolve_removes_from_pending(test_db):
    p = db.create_pipeline(name="pending-resolve")
    _set_next_run_at(p.id, datetime.utcnow() - timedelta(minutes=5))
    settings = _settings()
    detect_missed_runs(settings)
    assert get_pending() != []

    resolve(p.id)

    assert get_pending() == []


def test_resolve_unknown_pipeline_id_is_a_no_op(test_db):
    resolve(999999)   # ne doit pas lever
    assert get_pending() == []


def test_detect_clears_previous_pending_state(test_db):
    """Un second appel (ex. app relancée dans le même process de test) repart d'une liste
    propre plutôt que d'accumuler les détections précédentes."""
    p1 = db.create_pipeline(name="first-detection")
    _set_next_run_at(p1.id, datetime.utcnow() - timedelta(minutes=5))
    settings = _settings()
    detect_missed_runs(settings)
    assert len(get_pending()) == 1

    p2 = db.create_pipeline(name="second-detection")
    _set_next_run_at(p2.id, datetime.utcnow() - timedelta(minutes=5))
    # p1 n'a plus next_run_at dans le passé cette fois (déjà "replanifié" pour l'exemple).
    _set_next_run_at(p1.id, datetime.utcnow() + timedelta(hours=1))

    missed = detect_missed_runs(settings)

    assert [m["pipeline_id"] for m in missed] == [p2.id]
    assert [m["pipeline_id"] for m in get_pending()] == [p2.id]
