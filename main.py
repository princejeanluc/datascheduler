"""
DataScheduler — main.py
Point d'entrée de l'application.

Usage :
    python main.py
    ou (après packaging)
    DataScheduler.exe
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"


def _default_log_dir() -> Path:
    """Même racine que database/db_manager.py::get_db_path() — dupliqué volontairement
    (pas d'import croisé) pour que le logging se configure avant tout autre import lourd."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home())) / "DataScheduler"
    else:
        base = Path.home() / ".DataScheduler"
    return base / "logs"


def _configure_logging(log_dir: Path | None = None, log_filename: str = "app.log") -> None:
    """
    Console (comportement historique, inchangé) + fichier avec rotation. Avant ce correctif,
    le logging était uniquement console (StreamHandler par défaut de basicConfig) — perdu dès
    la fermeture de l'app, en particulier gênant pour le .exe packagé (pas de console visible).
    `log_dir` injectable pour les tests — sans argument, utilise le vrai %APPDATA%.

    `log_filename` distinct pour le worker en arrière-plan (chantier exécution en arrière-plan,
    "worker.log") — deux process ne doivent jamais écrire dans le même RotatingFileHandler, sa
    logique de rotation n'est pas sûre entre plusieurs process.
    """
    logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT, datefmt="%H:%M:%S")

    log_dir = log_dir or _default_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / log_filename, maxBytes=5_000_000, backupCount=5, encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt="%H:%M:%S"))
    logging.getLogger().addHandler(file_handler)


logger = logging.getLogger("DataScheduler")


def main():
    # Configuré ici plutôt qu'au niveau module : importer main.py (ex. depuis un test) ne
    # doit pas, en tant qu'effet de bord, écrire dans le vrai %APPDATA% de la machine —
    # seul un lancement réel de l'app (ce bloc) doit le faire.
    _configure_logging()
    logger.info("Démarrage DataScheduler")

    # Initialisation de la base SQLite
    from database.db_manager import init_db
    init_db()
    logger.info("Base de données initialisée")

    # Niveau de log — appliqué APRÈS la config initiale ci-dessus (elle doit rester capable de
    # capturer un souci pendant init_db() lui-même, donc ne peut pas dépendre de la base). La
    # rotation des fichiers (taille/nombre conservés), elle, reste figée à ce qui a été passé à
    # RotatingFileHandler ci-dessus — pas rechargée ici (voir ui/main_window/settings_view.py).
    from database.db_manager import get_app_settings
    app_settings = get_app_settings()
    logging.getLogger().setLevel(app_settings.log_level)

    # Chantier exécution en arrière-plan : en mode BACKGROUND, un worker détaché (voir
    # worker_main() ci-dessous) est le SEUL exécuteur — l'appli desktop ne doit ni réconcilier
    # les runs restés "en cours" (un run RUNNING peut très bien être un vrai run du worker,
    # pas un run interrompu par un crash) ni démarrer son propre scheduler, sous peine de deux
    # planificateurs actifs en même temps. En mode IN_APP (défaut), comportement historique
    # inchangé.
    scheduler = None
    if app_settings.execution_mode == "IN_APP":
        # Nettoyage des runs restés bloqués sur "en cours" suite à un arrêt brutal de
        # l'application précédente (crash, kill) — doit s'exécuter ici, avant que le scheduler
        # ne recommence à accepter de nouveaux runs (chantier N).
        from database.db_manager import reconcile_stale_runs
        n_reconciled = reconcile_stale_runs()
        if n_reconciled:
            logger.warning(
                "%d run(s) marqué(s) en échec (interrompus par un précédent arrêt de "
                "l'application).", n_reconciled,
            )

        # Détection des pipelines manqués (chantier rattrapage au démarrage) — DOIT s'exécuter
        # avant init_scheduler() ci-dessous : celui-ci recalcule next_run_at pour chaque
        # pipeline actif dès qu'il reconstruit les jobs, effaçant la trace de toute occurrence
        # manquée pendant que l'app était fermée. Sans jobstore persistant, c'est la seule
        # fenêtre où next_run_at reflète encore la session précédente.
        from core.missed_runs import detect_missed_runs
        missed = detect_missed_runs(app_settings)
        if missed:
            logger.warning(
                "%d pipeline(s) ont manqué leur exécution planifiée pendant l'arrêt de "
                "l'application.", len(missed),
            )

        from core.scheduler import init_scheduler
        scheduler = init_scheduler()
        logger.info("Scheduler démarré (%d pipeline(s) planifié(s))",
                    len(scheduler.list_jobs()))
    else:
        logger.info("Mode exécution en arrière-plan actif — aucun scheduler local démarré.")

    # Lancement de l'interface
    from ui.main_window import run
    run()

    # Arrêt propre du scheduler à la fermeture de l'UI
    if scheduler:
        scheduler.stop()
        logger.info("Scheduler arrêté")


def worker_main():
    """Point d'entrée du worker en arrière-plan (chantier exécution en arrière-plan) — lancé via
    `DataScheduler.exe --worker`, enregistré comme tâche planifiée Windows par
    ui/main_window/settings_view.py (voir core/task_scheduler.py). Aucun import ui.* : pas de
    boucle Qt, tourne indépendamment de toute session graphique."""
    _configure_logging(log_filename="worker.log")
    logger.info("Démarrage du worker DataScheduler (arrière-plan)")

    from database.db_manager import init_db
    init_db()
    logger.info("Base de données initialisée")

    from database.db_manager import get_app_settings, reconcile_stale_runs
    app_settings = get_app_settings()
    logging.getLogger().setLevel(app_settings.log_level)

    # Le worker est le seul exécuteur en mode BACKGROUND — c'est ici, et seulement ici, que la
    # réconciliation a un sens (tout run RUNNING trouvé au démarrage du worker est par
    # construction périmé, exactement comme pour l'appli desktop en mode IN_APP).
    n_reconciled = reconcile_stale_runs()
    if n_reconciled:
        logger.warning(
            "%d run(s) marqué(s) en échec (interrompus par un précédent arrêt du worker).",
            n_reconciled,
        )

    from core.scheduler import init_scheduler
    scheduler = init_scheduler()
    scheduler.refresh_command_poller()
    logger.info("Worker démarré (%d pipeline(s) planifié(s))", len(scheduler.list_jobs()))

    # Bloque jusqu'à une commande SHUTDOWN (voir core/scheduler.py::_poll_worker_commands),
    # déposée par l'appli desktop quand l'utilisateur repasse en mode "dans l'application
    # seulement" depuis Paramètres.
    scheduler.shutdown_requested.wait()

    scheduler.stop()
    logger.info("Worker arrêté")


if __name__ == "__main__":
    if "--worker" in sys.argv:
        worker_main()
    else:
        main()