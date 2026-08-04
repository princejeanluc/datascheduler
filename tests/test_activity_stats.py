"""
DataScheduler — tests/test_activity_stats.py
Vérifie db_manager.get_run_counts_by_day() (chantier UX statistiques/graphiques, B.1) : bucketing
par jour/statut, zéro-remplissage des jours sans exécution, bornes de la fenêtre `days` respectées.
"""

from datetime import datetime, timedelta

from database import db_manager as db
from database.models import PipelineRun


def _add_run(pipeline_id: int, started_at: datetime, status: str) -> None:
    with db.get_session() as s:
        s.add(PipelineRun(pipeline_id=pipeline_id, started_at=started_at, status=status))


def test_returns_one_entry_per_day_in_window(test_db):
    p = db.create_pipeline(name="stats-window")
    result = db.get_run_counts_by_day(days=7)
    assert len(result) == 7
    assert result[-1]["date"] == datetime.utcnow().date()
    assert result[0]["date"] == datetime.utcnow().date() - timedelta(days=6)


def test_zero_fills_days_without_runs(test_db):
    p = db.create_pipeline(name="stats-empty")
    result = db.get_run_counts_by_day(days=5)
    for entry in result:
        assert entry == {"date": entry["date"], "success": 0, "failed": 0, "cancelled": 0}


def test_buckets_by_day_and_status(test_db):
    p = db.create_pipeline(name="stats-bucket")
    today = datetime.utcnow()
    _add_run(p.id, today, "SUCCESS")
    _add_run(p.id, today, "SUCCESS")
    _add_run(p.id, today, "FAILED")
    _add_run(p.id, today - timedelta(days=2), "CANCELLED")

    result = db.get_run_counts_by_day(days=30)
    assert result[-1]["success"] == 2
    assert result[-1]["failed"] == 1
    assert result[-1]["cancelled"] == 0
    assert result[-3]["cancelled"] == 1


def test_excludes_runs_outside_window(test_db):
    p = db.create_pipeline(name="stats-outside")
    today = datetime.utcnow()
    _add_run(p.id, today - timedelta(days=40), "SUCCESS")

    result = db.get_run_counts_by_day(days=30)
    assert sum(r["success"] for r in result) == 0


def test_aggregates_across_all_pipelines(test_db):
    p1 = db.create_pipeline(name="stats-multi-1")
    p2 = db.create_pipeline(name="stats-multi-2")
    today = datetime.utcnow()
    _add_run(p1.id, today, "SUCCESS")
    _add_run(p2.id, today, "SUCCESS")

    result = db.get_run_counts_by_day(days=1)
    assert result[-1]["success"] == 2
