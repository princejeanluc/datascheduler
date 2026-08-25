"""
DataScheduler — tests/test_app_settings_scheduler_wiring.py
Chantier écran "Paramètres" : le fuseau horaire, la tolérance de rattrapage et le comportement
de regroupement des rattrapages manqués du scheduler APScheduler venaient jusqu'ici de
constantes câblées en dur (core/scheduler.py). Ce fichier verrouille qu'ils sont désormais lus
depuis AppSettings, et qu'apply_settings() répercute un changement sur tous les jobs déjà
planifiés sans attendre un redémarrage.

La deuxième moitié (chantier suivi des ressources) couvre le job d'échantillonnage CPU/mémoire :
enregistrement à l'intervalle configuré, ré-enregistrement par apply_settings(), et le
comportement de _sample_resources() (psutil mocké — pas de vraie mesure système en test).
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


def test_schedule_pipeline_uses_app_settings_timezone_not_os_local(test_db):
    """Bug réel signalé par l'utilisateur : un CronTrigger construit sans timezone= retombe
    silencieusement sur le fuseau local de l'OS (voir apscheduler.triggers.cron.CronTrigger.
    __init__), pas sur AppSettings.timezone — même si BackgroundScheduler(timezone=...) a bien
    reçu la bonne valeur, ce réglage ne s'applique jamais à un trigger déjà construit. Les
    pipelines s'exécutaient donc à l'heure OS exacte, mais next_run_at (recalculé dans ce
    fuseau OS) était ensuite réinterprété ailleurs (ex. core/missed_runs.py) comme s'il était
    dans AppSettings.timezone, d'où un décalage d'1h à 2h quand les deux fuseaux diffèrent."""
    db.update_app_settings(timezone="Europe/Paris")

    p = db.create_pipeline(name="tz-trigger-test")
    sched = PipelineScheduler()
    try:
        sched._schedule_pipeline(p)
        job = sched._scheduler.get_job(sched._job_id(p.id))
        assert str(job.trigger.timezone) == "Europe/Paris"
    finally:
        sched.stop()


def test_digest_job_uses_app_settings_timezone(test_db):
    db.update_app_settings(timezone="Europe/Paris")

    sched = PipelineScheduler()
    try:
        db.update_notification_settings(digest_enabled=True)
        sched.refresh_digest_job()
        job = sched._scheduler.get_job(sched.DIGEST_JOB_ID)
        assert str(job.trigger.timezone) == "Europe/Paris"
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


def test_schedule_pipeline_before_scheduler_started_does_not_raise(test_db):
    """add_job() sur un scheduler pas encore démarré réussit quand même (APScheduler journalise
    "Adding job tentatively...") mais ne calcule pas next_run_time tout de suite — Job utilise
    __slots__, donc lire cet attribut avant qu'il soit assigné lève AttributeError, pas None.
    Un vrai bug de terrain : le job était correctement enregistré, mais _schedule_pipeline()
    plantait quand même en tentant de relire next_run_time — ce qui, via load_all_pipelines(),
    faisait compter le pipeline comme "non planifié" (count jamais incrémenté) et empêchait la
    mise à jour de next_run_at en base, alors que le job était en réalité bien enregistré.
    Appel direct à _schedule_pipeline() (pas schedule_pipeline()) : le wrapper public avale déjà
    l'exception dans son propre try/except, ce qui masquerait la régression."""
    p = db.create_pipeline(name="not-yet-started-test")
    sched = PipelineScheduler()
    try:
        sched._schedule_pipeline(p)   # jamais sched.start() avant — ne doit pas lever

        job = sched._scheduler.get_job(sched._job_id(p.id))
        assert job is not None   # le job est bien enregistré malgré l'absence de next_run_time
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


# ──────────────────────────────────────────────
#  ÉCHANTILLONNAGE DES RESSOURCES (chantier suivi des ressources)
# ──────────────────────────────────────────────

def test_refresh_resource_sampler_registers_job_with_configured_interval(test_db):
    db.update_app_settings(resource_sample_interval_s=45)

    sched = PipelineScheduler()
    try:
        sched.start()
        sched.refresh_resource_sampler()

        job = sched._scheduler.get_job(sched.RESOURCE_SAMPLER_JOB_ID)
        assert job is not None
        assert job.trigger.interval.total_seconds() == 45
    finally:
        sched.stop()


def test_apply_settings_reregisters_resource_sampler_with_new_interval(test_db):
    sched = PipelineScheduler()
    try:
        sched.start()
        sched.refresh_resource_sampler()
        job = sched._scheduler.get_job(sched.RESOURCE_SAMPLER_JOB_ID)
        assert job.trigger.interval.total_seconds() == 60   # défaut

        db.update_app_settings(resource_sample_interval_s=10)
        sched.apply_settings()

        job = sched._scheduler.get_job(sched.RESOURCE_SAMPLER_JOB_ID)
        assert job.trigger.interval.total_seconds() == 10
    finally:
        sched.stop()


def test_load_all_pipelines_registers_resource_sampler(test_db):
    sched = PipelineScheduler()
    try:
        sched.start()
        sched.load_all_pipelines()
        assert sched._scheduler.get_job(sched.RESOURCE_SAMPLER_JOB_ID) is not None
    finally:
        sched.stop()


def test_sample_resources_records_a_sample_and_prunes_old_ones(test_db, monkeypatch):
    import core.scheduler as scheduler_module
    from datetime import datetime, timedelta
    from database.models import ResourceSample

    with db.get_session() as s:
        s.add(ResourceSample(timestamp=datetime.utcnow() - timedelta(days=30),
                              cpu_percent=1.0, memory_mb=100.0))
    db.update_app_settings(resource_sample_retention_days=7)

    class _FakeProcess:
        def cpu_percent(self, interval=None):
            return 12.5

        def memory_info(self):
            class _Mem:
                rss = 256_000_000   # 256 Mo
            return _Mem()

    fake_psutil = type("FakePsutil", (), {"Process": staticmethod(lambda: _FakeProcess())})
    monkeypatch.setitem(__import__("sys").modules, "psutil", fake_psutil)

    sched = PipelineScheduler()
    sched._sample_resources()

    samples = db.get_resource_samples(since=datetime.utcnow() - timedelta(minutes=1))
    assert len(samples) == 1
    assert samples[0].cpu_percent == 12.5
    assert samples[0].memory_mb == 256.0

    # L'échantillon vieux de 30 jours a été purgé (rétention 7 jours).
    all_samples = db.get_resource_samples(since=datetime.utcnow() - timedelta(days=60))
    assert len(all_samples) == 1


def test_sample_resources_never_raises_on_measurement_failure(test_db, monkeypatch):
    """Même logique que _run_digest : un souci de mesure ne doit jamais faire tomber le
    scheduler."""
    def _raise():
        raise OSError("mesure impossible")

    fake_psutil = type("FakePsutil", (), {"Process": staticmethod(_raise)})
    monkeypatch.setitem(__import__("sys").modules, "psutil", fake_psutil)

    sched = PipelineScheduler()
    sched._sample_resources()   # ne doit pas lever


# ──────────────────────────────────────────────
#  SONDAGE DES COMMANDES WORKER (chantier exécution en arrière-plan)
# ──────────────────────────────────────────────

def test_refresh_command_poller_registers_job(test_db):
    sched = PipelineScheduler()
    try:
        sched.start()
        sched.refresh_command_poller()
        job = sched._scheduler.get_job(sched.COMMAND_POLLER_JOB_ID)
        assert job is not None
        assert job.trigger.interval.total_seconds() == 3
    finally:
        sched.stop()


def test_poll_worker_commands_run_now_calls_trigger_now(test_db, monkeypatch):
    db.enqueue_worker_command("RUN_NOW", {"pipeline_id": 7})

    sched = PipelineScheduler()
    calls = []
    monkeypatch.setattr(sched, "trigger_now", lambda pid: calls.append(pid))

    sched._poll_worker_commands()

    assert calls == [7]
    assert db.get_pending_worker_commands() == []


def test_poll_worker_commands_reload_calls_load_all_pipelines(test_db, monkeypatch):
    db.enqueue_worker_command("RELOAD")

    sched = PipelineScheduler()
    calls = []
    monkeypatch.setattr(sched, "load_all_pipelines", lambda: calls.append(True))

    sched._poll_worker_commands()

    assert calls == [True]
    assert db.get_pending_worker_commands() == []


def test_poll_worker_commands_cancel_calls_request_cancel(test_db, monkeypatch):
    import core.pipeline as pipeline_module

    db.enqueue_worker_command("CANCEL", {"pipeline_id": 3})
    calls = []
    monkeypatch.setattr(pipeline_module, "request_cancel", lambda pid: calls.append(pid))

    sched = PipelineScheduler()
    sched._poll_worker_commands()

    assert calls == [3]
    assert db.get_pending_worker_commands() == []


def test_poll_worker_commands_shutdown_sets_event(test_db):
    db.enqueue_worker_command("SHUTDOWN")

    sched = PipelineScheduler()
    assert not sched.shutdown_requested.is_set()
    sched._poll_worker_commands()

    assert sched.shutdown_requested.is_set()
    assert db.get_pending_worker_commands() == []


def test_poll_worker_commands_never_raises_on_malformed_command(test_db):
    """Même logique défensive que _sample_resources/_run_digest : payload absent/invalide pour
    une commande qui en a besoin ne doit jamais faire tomber le sondage."""
    db.enqueue_worker_command("RUN_NOW")   # pas de payload -> KeyError interne, capturée

    sched = PipelineScheduler()
    sched._poll_worker_commands()   # ne doit pas lever

    # Marquée consommée malgré l'échec — jamais rejouée en boucle.
    assert db.get_pending_worker_commands() == []


def test_poll_worker_commands_ignores_unknown_command(test_db):
    db.enqueue_worker_command("BOGUS")

    sched = PipelineScheduler()
    sched._poll_worker_commands()   # ne doit pas lever

    assert db.get_pending_worker_commands() == []
