"""
DataScheduler — tests/test_app_settings_scheduler_wiring.py
Chantier écran "Paramètres" : le fuseau horaire, la tolérance de rattrapage et le comportement
de regroupement des rattrapages manqués du scheduler APScheduler venaient jusqu'ici de
constantes câblées en dur (core/scheduler.py). Ce fichier verrouille qu'ils sont désormais lus
depuis AppSettings, et qu'apply_settings() répercute un changement sur tous les jobs déjà
planifiés sans attendre un redémarrage.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from database import db_manager as db
from core.scheduler import PipelineScheduler


def test_scheduler_reads_timezone_from_app_settings(test_db):
    db.update_app_settings(timezone="Europe/Paris")

    sched = PipelineScheduler()
    try:
        assert str(sched._scheduler.timezone) == "Europe/Paris"
    finally:
        sched.stop()


def test_scheduler_defaults_to_utc_timezone(test_db):
    sched = PipelineScheduler()
    try:
        assert str(sched._scheduler.timezone) == "UTC"
    finally:
        sched.stop()


def test_schedule_pipeline_uses_app_settings_misfire_and_coalesce(test_db):
    db.update_app_settings(misfire_grace_time_min=15, coalesce_missed_runs=False)

    p = db.create_pipeline(name="wiring-test")
    sched = PipelineScheduler()
    try:
        sched.start()
        sched.schedule_pipeline(p.id)

        job = sched._scheduler.get_job(sched._job_id(p.id))
        assert job.misfire_grace_time == 15 * 60
        assert job.coalesce is False
    finally:
        sched.stop()


def test_apply_settings_reschedules_all_active_jobs_with_new_values(test_db):
    p1 = db.create_pipeline(name="wiring-test-1")
    p2 = db.create_pipeline(name="wiring-test-2")

    sched = PipelineScheduler()
    try:
        sched.start()
        sched.schedule_pipeline(p1.id)
        sched.schedule_pipeline(p2.id)

        # Valeurs par défaut au moment de la première planification.
        job1 = sched._scheduler.get_job(sched._job_id(p1.id))
        assert job1.misfire_grace_time == 60 * 60

        db.update_app_settings(misfire_grace_time_min=5, coalesce_missed_runs=False)
        sched.apply_settings()

        for pid in (p1.id, p2.id):
            job = sched._scheduler.get_job(sched._job_id(pid))
            assert job.misfire_grace_time == 5 * 60
            assert job.coalesce is False
    finally:
        sched.stop()
