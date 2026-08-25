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


# ──────────────────────────────────────────────
#  get_most_active_pipelines() — Historique, section "Fréquence d'exécution", passage à l'échelle
# ──────────────────────────────────────────────

def test_most_active_pipelines_orders_by_run_count_descending(test_db):
    quiet = db.create_pipeline(name="most-active-quiet")
    busy = db.create_pipeline(name="most-active-busy")
    today = datetime.utcnow()
    _add_run(quiet.id, today, "SUCCESS")
    for _ in range(3):
        _add_run(busy.id, today, "SUCCESS")

    result = db.get_most_active_pipelines(limit=10)
    names = [p.name for p in result]
    assert names.index("most-active-busy") < names.index("most-active-quiet")


def test_most_active_pipelines_respects_limit(test_db):
    for i in range(5):
        db.create_pipeline(name=f"most-active-limit-{i}")

    result = db.get_most_active_pipelines(limit=3)
    assert len(result) == 3


def test_most_active_pipelines_excludes_inactive(test_db):
    active = db.create_pipeline(name="most-active-on")
    inactive = db.create_pipeline(name="most-active-off")
    db.set_pipeline_active(inactive.id, False)
    today = datetime.utcnow()
    for _ in range(5):
        _add_run(inactive.id, today, "SUCCESS")

    result = db.get_most_active_pipelines(limit=10)
    names = [p.name for p in result]
    assert "most-active-on" in names
    assert "most-active-off" not in names


def test_most_active_pipelines_includes_pipelines_with_zero_runs(test_db):
    """L'agrégation est un outer join — un pipeline actif sans aucune exécution doit quand même
    apparaître (avec un compte de 0), pas être exclu par la jointure."""
    p = db.create_pipeline(name="most-active-idle")
    result = db.get_most_active_pipelines(limit=10)
    assert "most-active-idle" in [pp.name for pp in result]


def test_most_active_pipelines_respects_days_window(test_db):
    p1 = db.create_pipeline(name="most-active-recent")
    p2 = db.create_pipeline(name="most-active-stale")
    today = datetime.utcnow()
    _add_run(p1.id, today, "SUCCESS")
    _add_run(p2.id, today - timedelta(days=120), "SUCCESS")   # hors fenêtre de 90j par défaut

    result = db.get_most_active_pipelines(limit=10, days=90)
    names = [p.name for p in result]
    assert names.index("most-active-recent") < names.index("most-active-stale")


def test_most_active_pipelines_name_filter_lifts_the_default_limit(test_db):
    """Une recherche doit pouvoir révéler un pipeline peu actif que le plafond par défaut
    exclurait — limit=None quand name_filter est renseigné."""
    target = db.create_pipeline(name="rarely-run-report")
    for i in range(15):
        busy = db.create_pipeline(name=f"noise-{i}")
        _add_run(busy.id, datetime.utcnow(), "SUCCESS")

    capped = db.get_most_active_pipelines(limit=10)
    assert "rarely-run-report" not in [p.name for p in capped]

    filtered = db.get_most_active_pipelines(limit=None, name_filter="rarely-run")
    assert [p.name for p in filtered] == ["rarely-run-report"]


def test_most_active_pipelines_name_filter_is_case_insensitive_substring(test_db):
    db.create_pipeline(name="Rapport Mensuel")
    result = db.get_most_active_pipelines(limit=10, name_filter="rapport")
    assert "Rapport Mensuel" in [p.name for p in result]
