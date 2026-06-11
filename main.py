"""
DataScheduler — main.py
Point d'entrée de l'application.

Usage :
    python main.py
    ou (après packaging)
    DataScheduler.exe
"""

import sys
import logging
from pathlib import Path

# ── Logging ──────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("DataScheduler")


def main():
    logger.info("Démarrage DataScheduler")

    # Initialisation de la base SQLite
    from database.db_manager import init_db
    init_db()
    logger.info("Base de données initialisée")

    # Démarrage du scheduler en arrière-plan
    from core.scheduler import init_scheduler
    scheduler = init_scheduler()
    logger.info("Scheduler démarré (%d pipeline(s) planifié(s))",
                len(scheduler.list_jobs()))

    # Lancement de l'interface
    from ui.main_window import run
    run()

    # Arrêt propre du scheduler à la fermeture de l'UI
    scheduler.stop()
    logger.info("Scheduler arrêté")


if __name__ == "__main__":
    main()