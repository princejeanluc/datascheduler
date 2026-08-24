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
from datetime import datetime, timedelta
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
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
    DIGEST_JOB_ID = "digest_job"   # hors JOB_PREFIX : list_jobs() ne doit pas le compter comme un pipeline
    RESOURCE_SAMPLER_JOB_ID = "resource_sampler_job"   # idem — jamais compté comme un pipeline
    COMMAND_POLLER_JOB_ID = "command_poller_job"   # idem — jamais compté comme un pipeline

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
        # Fuseau horaire lu une seule fois, à la construction — le changer en cours de vie
        # n'est pas fiable pour les triggers déjà actifs (voir ui/main_window/settings_view.py),
        # donc un changement via l'écran Paramètres ne prend effet qu'au redémarrage de l'app.
        # Repli sur UTC si la base n'est pas encore prête (ne devrait pas arriver hors tests qui
        # construisent un PipelineScheduler sans passer par test_db).
        try:
            timezone = db.get_app_settings().timezone
        except RuntimeError:
            timezone = "UTC"
        self._scheduler      = BackgroundScheduler(timezone=timezone)
        self._on_job_success = on_job_success
        self._on_job_error   = on_job_error
        self._lock           = threading.Lock()
        # Positionné par une commande SHUTDOWN (chantier exécution en arrière-plan) — worker_main()
        # bloque dessus tant qu'aucun arrêt n'a été demandé depuis l'appli desktop cliente.
        # Existe même côté appli desktop (jamais utilisé là — inoffensif, évite un attribut
        # conditionnel).
        self.shutdown_requested = threading.Event()

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

        try:
            self.refresh_digest_job()
        except Exception as e:
            logger.error("Impossible de planifier le digest de notification : %s", e)

        try:
            self.refresh_resource_sampler()
        except Exception as e:
            logger.error("Impossible de planifier l'échantillonnage des ressources : %s", e)

        return count

    # ── Digest manager ────────────────────────

    def refresh_digest_job(self) -> None:
        """
        (Ré)enregistre ou retire le job de digest selon NotificationSettings actuel — appelé
        au démarrage et à chaque modification des paramètres de notification via l'UI, pour
        que le changement prenne effet sans redémarrer l'application.
        """
        settings = db.get_notification_settings()
        if not settings.digest_enabled:
            if self._scheduler.get_job(self.DIGEST_JOB_ID):
                self._scheduler.remove_job(self.DIGEST_JOB_ID)
                logger.info("Digest désactivé — job retiré.")
            return

        time_ = settings.digest_time or "07:00"
        try:
            hour, minute = [int(x) for x in time_.split(":")]
        except (ValueError, AttributeError):
            hour, minute = 7, 0

        if settings.digest_frequency == "WEEKLY":
            dow = settings.digest_day_of_week if settings.digest_day_of_week is not None else 0
            trigger = CronTrigger(day_of_week=dow, hour=hour, minute=minute)
        else:
            trigger = CronTrigger(hour=hour, minute=minute)

        self._scheduler.add_job(
            func=self._run_digest,
            trigger=trigger,
            id=self.DIGEST_JOB_ID,
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
        )
        logger.info(
            "Digest de notification planifié (%s, %02d:%02d).",
            settings.digest_frequency, hour, minute,
        )

    def _run_digest(self) -> None:
        """Cible du job de digest — lit NotificationSettings, envoie un résumé des exécutions
        depuis le dernier envoi si des runs existent. Ne lève jamais d'exception (comme
        _run_scheduled_pipeline) : une erreur d'envoi est loguée, jamais fatale au scheduler."""
        try:
            settings = db.get_notification_settings()
            if not settings.digest_enabled:
                return
            if not settings.digest_smtp_profile_id or not settings.digest_recipients:
                logger.warning("Digest activé mais profil SMTP ou destinataires manquants — ignoré.")
                return

            smtp_profile = db.get_smtp_profile(settings.digest_smtp_profile_id)
            if not smtp_profile:
                logger.warning("Digest : profil SMTP introuvable (id=%s).",
                                settings.digest_smtp_profile_id)
                return

            since = settings.digest_last_sent_at or (datetime.utcnow() - timedelta(days=1))
            runs = [r for r in db.get_recent_runs(limit=500)
                    if r.started_at and r.started_at >= since]
            if not runs:
                db.update_notification_settings(digest_last_sent_at=datetime.utcnow())
                return

            body = self._build_digest_body(runs)

            from core.email import EmailSender, config_from_profile
            recipients = [addr.strip() for addr in settings.digest_recipients.split(",") if addr.strip()]
            sender = EmailSender(config_from_profile(smtp_profile))
            result = sender.send(recipients, "DataScheduler — résumé des exécutions", body)

            if result.success:
                db.update_notification_settings(digest_last_sent_at=datetime.utcnow())
                logger.info("Digest envoyé à %s (%d run(s)).", recipients, len(runs))
            else:
                logger.error("Échec envoi digest : %s", result.error)

        except Exception as e:
            logger.exception("Erreur inattendue lors du digest : %s", e)

    @staticmethod
    def _build_digest_body(runs: list) -> str:
        def status_str(val):
            return val.value if hasattr(val, "value") else str(val or "IDLE")

        success = [r for r in runs if status_str(r.status) == "SUCCESS"]
        failed  = [r for r in runs if status_str(r.status) == "FAILED"]

        lines = [
            f"Résumé DataScheduler — {len(runs)} exécution(s) depuis le dernier envoi.",
            "",
            f"Succès : {len(success)}",
            f"Échecs : {len(failed)}",
        ]
        if failed:
            lines.append("")
            lines.append("Détail des échecs :")
            for r in failed:
                pname = r.pipeline.name if r.pipeline else str(r.pipeline_id)
                when  = r.started_at.strftime("%d/%m/%Y %H:%M") if r.started_at else "—"
                lines.append(f"  - {pname} ({when}) : {r.error_message or 'erreur inconnue'}")
        return "\n".join(lines)

    # ── Échantillonnage des ressources (vue Ressources) ──

    def refresh_resource_sampler(self) -> None:
        """(Ré)enregistre le job d'échantillonnage CPU/mémoire selon AppSettings.
        resource_sample_interval_s — appelé au démarrage et depuis apply_settings() si
        l'intervalle change, même patron que refresh_digest_job() ci-dessus. Contrairement au
        digest, jamais désactivable : tourne tant que l'appli est ouverte."""
        interval = db.get_app_settings().resource_sample_interval_s
        self._scheduler.add_job(
            func=self._sample_resources,
            trigger=IntervalTrigger(seconds=interval),
            id=self.RESOURCE_SAMPLER_JOB_ID,
            replace_existing=True,
            misfire_grace_time=interval,
            coalesce=True,
        )
        logger.info("Échantillonnage des ressources planifié (toutes les %ds).", interval)

    def _sample_resources(self) -> None:
        """Cible du job d'échantillonnage — mesure CPU/mémoire du process DataScheduler
        (jamais par pipeline : ils tournent en threads dans ce même process, impossible à
        attribuer proprement, voir ui/main_window/resources_view.py) puis purge les échantillons
        expirés selon la rétention courante, dans le même appel plutôt qu'un job de purge
        séparé. Ne lève jamais d'exception (même logique que _run_digest) : un souci de mesure
        ne doit jamais faire tomber le scheduler."""
        try:
            import psutil

            process = psutil.Process()
            cpu_percent = process.cpu_percent(interval=None)
            memory_mb = process.memory_info().rss / 1_000_000
            db.record_resource_sample(cpu_percent, memory_mb)

            settings = db.get_app_settings()
            cutoff = datetime.utcnow() - timedelta(days=settings.resource_sample_retention_days)
            db.prune_resource_samples(cutoff)
        except Exception as e:
            logger.warning("Échec de l'échantillonnage des ressources (ignoré) : %s", e)

    # ── Sondage des commandes (chantier exécution en arrière-plan) ──

    def refresh_command_poller(self) -> None:
        """Enregistre le job qui lit WorkerCommand — appelé UNIQUEMENT par worker_main() (voir
        main.py), jamais par le process desktop : l'appli desktop dépose des commandes dans
        cette file, elle ne doit jamais les consommer elle-même."""
        self._scheduler.add_job(
            func=self._poll_worker_commands,
            trigger=IntervalTrigger(seconds=3),
            id=self.COMMAND_POLLER_JOB_ID,
            replace_existing=True,
            misfire_grace_time=3,
            coalesce=True,
        )
        logger.info("Sondage des commandes worker planifié (toutes les 3s).")

    def _poll_worker_commands(self) -> None:
        """Cible du job de sondage — traite chaque commande en attente puis la marque
        consommée. Ne lève jamais (même logique que _run_digest/_sample_resources) : une
        commande malformée ne doit jamais faire tomber le worker."""
        import json

        for cmd in db.get_pending_worker_commands():
            try:
                payload = json.loads(cmd.payload_json) if cmd.payload_json else {}
                if cmd.command == "RUN_NOW":
                    self.trigger_now(payload["pipeline_id"])
                elif cmd.command == "RELOAD":
                    self.load_all_pipelines()
                elif cmd.command == "CANCEL":
                    from core.pipeline import request_cancel
                    request_cancel(payload["pipeline_id"])
                elif cmd.command == "SHUTDOWN":
                    self.shutdown_requested.set()
                else:
                    logger.warning("Commande worker inconnue ignorée : %s", cmd.command)
            except Exception as e:
                logger.warning("Échec du traitement de la commande worker %s (ignoré) : %s",
                                cmd.id, e)
            finally:
                db.mark_worker_command_consumed(cmd.id)

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

    def apply_settings(self) -> None:
        """Réapplique AppSettings (tolérance de rattrapage, coalesce, intervalle
        d'échantillonnage des ressources) à tous les jobs déjà planifiés — appelé par l'écran
        Paramètres après enregistrement. Le fuseau horaire, lui, n'est lu qu'à la construction du
        scheduler (voir __init__) et ne peut pas être appliqué à chaud ici — redémarrage requis
        pour celui-là. Même patron que refresh_digest_job(), généralisé à tous les jobs plutôt
        qu'à un seul."""
        for job in self.list_jobs():
            self.schedule_pipeline(job["pipeline_id"])
        self.refresh_resource_sampler()

    # ── Interne ──────────────────────────────

    def _job_id(self, pipeline_id: int) -> str:
        return f"{self.JOB_PREFIX}{pipeline_id}"

    def _run_scheduled_pipeline(self, pipeline_id: int) -> None:
        """
        Wrapper utilisé comme cible du job APScheduler — run_pipeline() ne lève jamais
        d'exception (elle capture tout en interne et retourne un PipelineResult), donc
        APScheduler ne voit jamais EVENT_JOB_ERROR pour un échec propre : sans ce wrapper,
        un run planifié qui échoue normalement (pas un crash) ne déclenche ni
        on_job_success ni on_job_error. Même logique que trigger_now()._run() ci-dessus,
        appliquée uniformément aux runs planifiés (pas seulement au lancement manuel).
        """
        from core.pipeline import run_pipeline
        result = run_pipeline(pipeline_id)
        if result.success and self._on_job_success:
            self._on_job_success(pipeline_id, result.remote_path)
        elif not result.success and self._on_job_error:
            self._on_job_error(pipeline_id, result.error)

    def _schedule_pipeline(self, pipeline) -> None:
        """Ajoute ou remplace le job APScheduler pour ce pipeline."""
        job_id  = self._job_id(pipeline.id)
        trigger = build_cron_trigger(pipeline)
        settings = db.get_app_settings()

        # add_job avec replace_existing=True pour la mise à jour à chaud
        self._scheduler.add_job(
            func=self._run_scheduled_pipeline,
            trigger=trigger,
            id=job_id,
            args=[pipeline.id],
            kwargs={},
            name=pipeline.name,
            replace_existing=True,
            misfire_grace_time=settings.misfire_grace_time_min * 60,
            coalesce=settings.coalesce_missed_runs,
        )

        # add_job() a réussi (le job est planifié) même si le scheduler n'est pas encore
        # `running` à cet instant précis — APScheduler journalise alors "Adding job
        # tentatively..." et ne calcule PAS next_run_time tout de suite (Job utilise
        # __slots__ : lire un attribut jamais assigné lève AttributeError, pas None). Sans
        # cette garde, ce cas normal-mais-transitoire faisait planter toute la fonction —
        # le pipeline était donc compté comme "non planifié" et next_run_at n'était jamais mis
        # à jour en base, alors que le job était en réalité bien enregistré.
        job = self._scheduler.get_job(job_id)
        next_run = getattr(job, "next_run_time", None)
        logger.info(
            "Pipeline planifié : %s (%s) → prochaine exéc. : %s",
            pipeline.name, describe_schedule(pipeline),
            next_run or "à déterminer au démarrage du scheduler",
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