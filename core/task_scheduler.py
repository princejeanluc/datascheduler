"""
DataScheduler — core/task_scheduler.py
Enregistrement/désinscription de la tâche planifiée Windows qui lance le worker en arrière-plan
(chantier exécution en arrière-plan) — voir ui/main_window/settings_view.py pour la bascule de
mode qui appelle ces fonctions.

Choix délibéré : `schtasks.exe` (intégré à Windows, invoqué en sous-process) plutôt que l'API COM
du Planificateur de tâches (pywin32) — pas de nouvelle dépendance, et surtout `/sc onlogon` sans
`/ru` (utilisateur cible) s'enregistre pour l'utilisateur COURANT avec ses droits existants,
`/rl limited` demande explicitement le niveau limité plutôt qu'élevé : aucune élévation
administrateur requise, contrairement à un vrai service Windows (écarté en discussion avec
l'utilisateur pour cette raison précise).
"""

import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

TASK_NAME = "DataSchedulerWorker"


def _worker_command_line() -> str:
    """Chemin de l'exécutable courant + l'indicateur --worker — fonctionne aussi bien pour
    l'exe gelé (sys.executable = DataScheduler.exe) que pour un lancement depuis les sources
    (sys.executable = python.exe, dans quel cas main.py doit être passé explicitement)."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --worker'
    return f'"{sys.executable}" "{sys.argv[0]}" --worker'


def register_logon_task() -> bool:
    """Enregistre (ou remplace, /f) la tâche qui lance le worker à l'ouverture de session.
    Ne lève jamais — un échec est journalisé, pas fatal (l'appli reste utilisable, l'écran
    Paramètres reflète l'état réel via le battement de cœur, pas via cette valeur de retour)."""
    try:
        subprocess.run(
            [
                "schtasks", "/create", "/tn", TASK_NAME,
                "/tr", _worker_command_line(),
                "/sc", "onlogon",
                "/rl", "limited",
                "/f",
            ],
            check=True, capture_output=True, text=True,
        )
        logger.info("Tâche planifiée '%s' enregistrée.", TASK_NAME)
        return True
    except Exception as e:
        logger.error("Échec de l'enregistrement de la tâche planifiée '%s' : %s", TASK_NAME, e)
        return False


def unregister_logon_task() -> bool:
    """Retire la tâche — no-op silencieux si elle n'existe déjà plus (bascule répétée,
    installation qui n'a jamais activé le mode arrière-plan)."""
    try:
        result = subprocess.run(
            ["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            logger.info("Tâche planifiée '%s' retirée.", TASK_NAME)
        return True
    except Exception as e:
        logger.error("Échec du retrait de la tâche planifiée '%s' : %s", TASK_NAME, e)
        return False
