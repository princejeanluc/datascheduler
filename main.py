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


def _configure_logging(log_dir: Path | None = None) -> None:
    """
    Console (comportement historique, inchangé) + fichier avec rotation. Avant ce correctif,
    le logging était uniquement console (StreamHandler par défaut de basicConfig) — perdu dès
    la fermeture de l'app, en particulier gênant pour le .exe packagé (pas de console visible).
    `log_dir` injectable pour les tests — sans argument, utilise le vrai %APPDATA%.
    """
    logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT, datefmt="%H:%M:%S")

    log_dir = log_dir or _default_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "app.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8",
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