"""
DataScheduler — core/scheduler.py
Gestion du planificateur APScheduler.

Responsabilités :
  - Démarrer / arrêter le scheduler en arrière-plan
  - Charger tous les pipelines actifs depuis la DB
  - Calculer l'expression cron selon la fréquence (DAILY/WEEKLY/MONTHLY/CUSTOM)
  - Ajouter / retirer / mettre à jour les jobs à chaud
  - Émettre des événements pour que l'UI se mette à jour
"""

import logging
import threading
from datetime import datetime
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import (
    EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED,
)

from database import db_manager as db

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  CALCUL DES EXPRESSIONS CRON
# ──────────────────────────────────────────────

def build_cron_trigger(pipeline) -> CronTrigger:
    """
    Construit un CronTrigger APScheduler depuis la config d'un Pipeline.

    Fréquences supportées :
        DAILY    → tous les jours à scheduled_time (HH:MM)
        WEEKLY   → scheduled_day (0=lun…6=dim) à scheduled_time
        MONTHLY  → scheduled_day (1-31) du mois à scheduled_time
        CUSTOM   → cron_expression brute (ex: "0 6 * * 1-5")

    Exemples :
        DAILY  / 06:00              → "0 6 * * *"
        WEEKLY / lundi / 08:00      → "0 8 * * 0"
        MONTHLY / 1er / 03:00       → "0 3 1 * *"
        CUSTOM / "30 5 * * 1,3,5"  → "30 5 * * 1,3,5"
    """
    freq  = str(pipeline.frequency).replace("CronFrequency.", "")
    time_ = pipeline.scheduled_time or "06:00"          # défaut 06:00
    day_  = pipeline.scheduled_day

    try:
        hour, minute = [int(x) for x in time_.split(":")]
    except (ValueError, AttributeError):
        hour, minute = 6, 0

    if freq == "CUSTOM":
        expr = pipeline.cron_expression or "0 6 * * *"
        parts = expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Expression cron invalide : '{expr}' (attendu 5 champs)")
        return CronTrigger(
            minute=parts[0], hour=parts[1],
            day=parts[2], month=parts[3], day_of_week=parts[4],
        )

    if freq == "DAILY":
        return CronTrigger(hour=hour, minute=minute)

    if freq == "WEEKLY":
        dow = int(day_) if day_ is not None else 0   # 0 = lundi
        return CronTrigger(day_of_week=dow, hour=hour, minute=minute)

    if freq == "MONTHLY":
        dom = int(day_) if day_ is not None else 1
        return CronTrigger(day=dom, hour=hour, minute=minute)

    raise ValueError(f"Fréquence inconnue : {freq}")


def describe_schedule(pipeline) -> str:
    """
    Retourne une description lisible de la planification.
    Ex : "Quotidien 06:00", "Lundi 08:00", "Le 1er du mois 03:00"
    """
    freq  = str(pipeline.frequency).replace("CronFrequency.", "")
    time_ = pipeline.scheduled_time or "06:00"
    day_  = pipeline.scheduled_day

    DAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]

    if freq == "DAILY":
        return f"Quotidien {time_}"
    if freq == "WEEKLY":
        d = DAYS[int(day_)] if day_ is not None else "Lun"
        return f"{d} {time_}"
    if freq == "MONTHLY":
        d = int(day_) if day_ is not None else 1
        return f"Le {d} du mois {time_}"
    if freq == "CUSTOM":
        return pipeline.cron_expression or "—"
    return "—"


# ──────────────────────────────────────────────
#  SCHEDULER SINGLETON
# ──────────────────────────────────────────────

class PipelineScheduler:
    """
    Wrapper autour de APScheduler BackgroundScheduler.

    Usage :
        scheduler = PipelineScheduler()
        scheduler.start()
        scheduler.load_all_pipelines()
        ...
        scheduler.stop()

    Thread-safe — APScheduler gère lui-même le locking interne.
    """

    JOB_PREFIX = "pipeline_"

    def __init__(
        self,
        on_job_success: Callable[[int, str], None] | None = None,
        on_job_error:   Callable[[int, str], None] | None = None,
    ):
        """
        Paramètres :
            on_job_success(pipeline_id, remote_path) — appelé après succès
            on_job_error(pipeline_id, error_msg)     — appelé après échec
        """
        self._scheduler      = BackgroundScheduler(timezone="UTC")
        self._on_job_success = on_job_success
        self._on_job_error   = on_job_error
        self._lock           = threading.Lock()

        # Écouter les événements APScheduler
        self._scheduler.add_listener(
            self._on_apscheduler_event,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED,
        )

    # ── Lifecycle ────────────────────────────

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("Scheduler démarré.")

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler arrêté.")

    @property
    def is_running(self) -> bool:
        return self._scheduler.running

    # ── Chargement initial ───────────────────

    def load_all_pipelines(self) -> int:
        """
        Charge tous les pipelines actifs depuis la DB et planifie leurs jobs.
        Retourne le nombre de jobs ajoutés.
        """
        pipelines = db.get_pipelines(active_only=True)
        count = 0
        for p in pipelines:
            try:
                self._schedule_pipeline(p)
                count += 1
            except Exception as e:
                logger.error("Impossible de planifier pipeline %s : %s", p.name, e)
        logger.info("%d pipeline(s) planifié(s).", count)
        return count

    # ── Gestion des jobs individuels ─────────

    def schedule_pipeline(self, pipeline_id: int) -> bool:
        """
        Ajoute ou met à jour le job pour un pipeline.
        Retourne True si OK.
        """
        pipeline = db.get_pipeline(pipeline_id)
        if not pipeline:
            logger.warning("Pipeline %d introuvable.", pipeline_id)
            return False
        if not pipeline.is_active:
            self.remove_pipeline(pipeline_id)
            return False
        try:
            self._schedule_pipeline(pipeline)
            return True
        except Exception as e:
            logger.error("Erreur planification pipeline %d : %s", pipeline_id, e)
            return False

    def remove_pipeline(self, pipeline_id: int) -> bool:
        """Supprime le job d'un pipeline du scheduler."""
        job_id = self._job_id(pipeline_id)
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            logger.info("Job supprimé : %s", job_id)
            return True
        return False

    def trigger_now(self, pipeline_id: int) -> bool:
        """
        Exécute un pipeline immédiatement (hors planification).
        Lance dans un thread séparé pour ne pas bloquer l'UI.
        Retourne True si le lancement est parti.
        """
        pipeline = db.get_pipeline(pipeline_id)
        if not pipeline:
            return False

        def _run():
            from core.pipeline import run_pipeline
            logger.info("Exécution manuelle du pipeline %d (%s)",
                        pipeline_id, pipeline.name)
            result = run_pipeline(pipeline_id)
            if result.success and self._on_job_success:
                self._on_job_success(pipeline_id, result.remote_path)
            elif not result.success and self._on_job_error:
                self._on_job_error(pipeline_id, result.error)

        t = threading.Thread(target=_run, daemon=True,
                             name=f"manual_pipeline_{pipeline_id}")
        t.start()
        return True

    def get_next_run(self, pipeline_id: int) -> datetime | None:
        """Retourne la prochaine date d'exécution planifiée, ou None."""
        job = self._scheduler.get_job(self._job_id(pipeline_id))
        if job and job.next_run_time:
            return job.next_run_time
        return None

    def list_jobs(self) -> list[dict]:
        """Retourne la liste des jobs actifs avec leur prochaine exécution."""
        jobs = []
        for job in self._scheduler.get_jobs():
            if job.id.startswith(self.JOB_PREFIX):
                pipeline_id = int(job.id[len(self.JOB_PREFIX):])
                jobs.append({
                    "pipeline_id": pipeline_id,
                    "job_id":      job.id,
                    "next_run":    job.next_run_time,
                })
        return jobs

    # ── Interne ──────────────────────────────

    def _job_id(self, pipeline_id: int) -> str:
        return f"{self.JOB_PREFIX}{pipeline_id}"

    def _schedule_pipeline(self, pipeline) -> None:
        """Ajoute ou remplace le job APScheduler pour ce pipeline."""
        from core.pipeline import run_pipeline

        job_id  = self._job_id(pipeline.id)
        trigger = build_cron_trigger(pipeline)

        # add_job avec replace_existing=True pour la mise à jour à chaud
        self._scheduler.add_job(
            func=run_pipeline,
            trigger=trigger,
            id=job_id,
            args=[pipeline.id],
            kwargs={},
            name=pipeline.name,
            replace_existing=True,
            misfire_grace_time=3600,   # 1h de tolérance si le PC était éteint
            coalesce=True,             # ne pas rattraper les exécutions manquées
        )

        next_run = self._scheduler.get_job(job_id).next_run_time
        logger.info(
            "Pipeline planifié : %s (%s) → prochaine exéc. : %s",
            pipeline.name, describe_schedule(pipeline), next_run
        )

        # Mettre à jour next_run_at en DB
        with db.get_session() as s:
            from database.models import Pipeline
            p = s.get(Pipeline, pipeline.id)
            if p and next_run:
                p.next_run_at = next_run.replace(tzinfo=None)

    def _on_apscheduler_event(self, event) -> None:
        """Listener APScheduler — dispatch vers les callbacks UI."""
        if not event.job_id.startswith(self.JOB_PREFIX):
            return

        pipeline_id = int(event.job_id[len(self.JOB_PREFIX):])

        if event.code == EVENT_JOB_ERROR:
            msg = str(event.exception) if event.exception else "Erreur inconnue"
            logger.error("Job %s échoué : %s", event.job_id, msg)
            if self._on_job_error:
                self._on_job_error(pipeline_id, msg)

        elif event.code == EVENT_JOB_MISSED:
            logger.warning("Job %s manqué (PC éteint ?)", event.job_id)

        # EVENT_JOB_EXECUTED = job lancé sans exception APScheduler
        # (le résultat réel du pipeline est géré dans run_pipeline lui-même)


# ──────────────────────────────────────────────
#  INSTANCE GLOBALE (singleton d'application)
# ──────────────────────────────────────────────

_scheduler_instance: PipelineScheduler | None = None


def get_scheduler() -> PipelineScheduler:
    """Retourne l'instance globale du scheduler (à créer avec init_scheduler)."""
    if _scheduler_instance is None:
        raise RuntimeError("Scheduler non initialisé. Appelle init_scheduler() au démarrage.")
    return _scheduler_instance


def init_scheduler(
    on_job_success: Callable | None = None,
    on_job_error:   Callable | None = None,
) -> PipelineScheduler:
    """
    Initialise et démarre le scheduler global.
    À appeler une seule fois au démarrage de l'application (dans main.py).
    """
    global _scheduler_instance
    _scheduler_instance = PipelineScheduler(
        on_job_success=on_job_success,
        on_job_error=on_job_error,
    )
    _scheduler_instance.start()
    _scheduler_instance.load_all_pipelines()
    return _scheduler_instance