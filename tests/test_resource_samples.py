"""
DataScheduler — tests/test_resource_samples.py
Chantier suivi des ressources : record_resource_sample/get_resource_samples/
prune_resource_samples (historique CPU/mémoire de l'appli) et get_runs_overlapping_window
(réutilisée pour compter les pipelines en cours à un instant donné et pour le détail au survol
de la vue Ressources).
"""

from datetime import datetime, timedelta

from database import db_manager as db


def test_record_and_get_resource_samples_orders_chronologically(test_db):
    now = datetime.utcnow()
    db.record_resource_sample(cpu_percent=10.0, memory_mb=200.0)
    db.record_resource_sample(cpu_percent=20.0, memory_mb=210.0)

    samples = db.get_resource_samples(since=now - timedelta(minutes=1))

    assert len(samples) == 2
    assert samples[0].timestamp <= samples[1].timestamp
    assert samples[0].cpu_percent == 10.0


def test_get_resource_samples_excludes_samples_before_since(test_db):
    from database.models import ResourceSample
    with db.get_session() as s:
        s.add(ResourceSample(timestamp=datetime.utcnow() - timedelta(days=2),
                              cpu_percent=5.0, memory_mb=100.0))
    db.record_resource_sample(cpu_percent=15.0, memory_mb=150.0)

    samples = db.get_resource_samples(since=datetime.utcnow() - timedelta(hours=1))

    assert len(samples) == 1
    assert samples[0].cpu_percent == 15.0


def test_prune_resource_samples_removes_only_older_ones(test_db):
    from database.models import ResourceSample
    with db.get_session() as s:
        s.add(ResourceSample(timestamp=datetime.utcnow() - timedelta(days=10),
                              cpu_percent=1.0, memory_mb=100.0))
    db.record_resource_sample(cpu_percent=2.0, memory_mb=110.0)   # récent, doit survivre

    removed = db.prune_resource_samples(older_than=datetime.utcnow() - timedelta(days=7))

    assert removed == 1
    remaining = db.get_resource_samples(since=datetime.utcnow() - timedelta(days=30))
    assert len(remaining) == 1
    assert remaining[0].cpu_percent == 2.0


def test_get_runs_overlapping_window_includes_still_running_run(test_db):
    """Un run avec finished_at NULL (encore en cours) doit être considéré comme chevauchant
    toute fenêtre postérieure à son démarrage, pas seulement l'instant présent."""
    pipeline = db.create_pipeline(name="overlap-test")
    run = db.create_run(pipeline.id)   # finished_at reste NULL

    window_start = datetime.utcnow() - timedelta(minutes=5)
    window_end = datetime.utcnow() + timedelta(minutes=5)
    runs = db.get_runs_overlapping_window(window_start, window_end)

    assert any(r.id == run.id for r in runs)


def test_get_runs_overlapping_window_excludes_runs_finished_before_window(test_db):
    from database.models import PipelineRun
    pipeline = db.create_pipeline(name="overlap-exclude-test")
    run = db.create_run(pipeline.id)
    with db.get_session() as s:
        r = s.get(PipelineRun, run.id)
        r.started_at = datetime.utcnow() - timedelta(hours=3)
        r.finished_at = datetime.utcnow() - timedelta(hours=2)

    window_start = datetime.utcnow() - timedelta(minutes=30)
    window_end = datetime.utcnow()
    runs = db.get_runs_overlapping_window(window_start, window_end)

    assert not any(r.id == run.id for r in runs)


def test_get_runs_overlapping_window_includes_run_started_before_and_ended_inside(test_db):
    from database.models import PipelineRun
    pipeline = db.create_pipeline(name="overlap-partial-test")
    run = db.create_run(pipeline.id)
    with db.get_session() as s:
        r = s.get(PipelineRun, run.id)
        r.started_at = datetime.utcnow() - timedelta(hours=2)
        r.finished_at = datetime.utcnow() - timedelta(minutes=10)

    window_start = datetime.utcnow() - timedelta(minutes=30)
    window_end = datetime.utcnow()
    runs = db.get_runs_overlapping_window(window_start, window_end)

    assert any(r.id == run.id for r in runs)
