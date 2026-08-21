"""
DataScheduler — core/task_scheduler.py
Enregistrement/désinscription de la tâche planifiée Windows qui lance le worker en arrière-plan
(chantier exécution en arrière-plan) — voir ui/main_window/settings_view.py pour la bascule de
mode qui appelle ces fonctions.

Choix délibéré : `schtasks.exe` (intégré à Windows, invoqué en sous-process) plutôt que l'API COM
du Planificateur de tâches (pywin32) — pas de nouvelle dépendance, et surtout `/rl limited` +
`LogonType=InteractiveToken` (dans la définition XML ci-dessous) demandent explicitement le
niveau limité et l'exécution avec le jeton de l'utilisateur interactif COURANT : aucune élévation
administrateur requise, aucun mot de passe stocké — contrairement à un vrai service Windows
(écarté en discussion avec l'utilisateur pour cette raison précise).

Deux déclencheurs sur la MÊME tâche (nécessite `/xml`, un `schtasks /create /sc ...` classique
n'accepte qu'un seul déclencheur par appel) :
- connexion (`LogonTrigger`) : démarrage immédiat à l'ouverture de session, comme avant.
- répétition périodique (`TimeTrigger` + `Repetition`, watchdog) : filet de sécurité qui relance
  le worker s'il a planté ou n'a jamais démarré (ex. app fermée puis rouverte sans déconnexion
  Windows entre-temps — cas déjà rencontré en test réel), sans jamais lancer une deuxième
  instance en parallèle d'une déjà active, grâce à `MultipleInstancesPolicy=IgnoreNew` : si le
  worker tourne déjà, ce déclencheur ne fait rien. Deux tâches séparées (une par déclencheur)
  auraient chacune leur propre politique multi-instance et pourraient donc se lancer en double —
  d'où la définition XML unique plutôt que deux `schtasks /create` distincts.
"""

import logging
import os
import subprocess
import sys
import tempfile
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)

TASK_NAME = "DataSchedulerWorker"

# Filet de sécurité, pas un réglage utilisateur (voir la discussion dans la session qui a
# introduit ce watchdog) : la plupart des types de déclencheur schtasks (daily/weekly/monthly/
# once/onidle/hourly) sont pensés pour des tâches "s'exécute puis s'arrête", pas pour un daemon
# persistant — les exposer à l'utilisateur n'aurait ajouté que de la complexité sans bénéfice
# réel. Un seul intervalle fixe, raisonnable pour un worker censé être quasi toujours actif.
WATCHDOG_INTERVAL_MINUTES = 5


def _worker_command_and_args() -> tuple[str, str]:
    """(chemin de l'exécutable, arguments) séparés — la définition XML d'une action <Exec> attend
    <Command>/<Arguments> distincts, contrairement à la ligne `/tr` d'un `schtasks /create`
    classique. Fonctionne aussi bien pour l'exe gelé (sys.executable = DataScheduler.exe) que
    pour un lancement depuis les sources (sys.executable = python.exe, main.py passé en argument).
    Chemins toujours ABSOLUS (`os.path.abspath`) : le Planificateur de tâches Windows n'hérite pas
    forcément du répertoire de travail courant au déclenchement — un chemin relatif comme
    "main.py" ne serait alors résolu nulle part."""
    exe = os.path.abspath(sys.executable)
    if getattr(sys, "frozen", False):
        return exe, "--worker"
    return exe, f'"{os.path.abspath(sys.argv[0])}" --worker'


def _task_xml() -> str:
    """Définition de tâche complète (voir la docstring de module pour le pourquoi de l'XML
    plutôt qu'un `schtasks /create /sc ...` classique). `ExecutionTimeLimit` est explicitement
    à PT0S (illimité) : la limite PAR DÉFAUT d'une tâche définie en XML est PT72H (3 jours) —
    sans cette ligne, Windows tuerait silencieusement le worker au bout de 3 jours d'activité
    continue, une régression qui aurait été très difficile à relier à cette cause."""
    command, arguments = _worker_command_and_args()
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
    <TimeTrigger>
      <StartBoundary>2020-01-01T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <Repetition>
        <Interval>PT{WATCHDOG_INTERVAL_MINUTES}M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(command)}</Command>
      <Arguments>{escape(arguments)}</Arguments>
    </Exec>
  </Actions>
</Task>"""


def register_logon_task() -> bool:
    """Enregistre (ou remplace, /f) la tâche qui lance le worker à l'ouverture de session ET la
    relance périodiquement si elle n'est plus active (watchdog, voir WATCHDOG_INTERVAL_MINUTES).
    Ne lève jamais — un échec est journalisé, pas fatal (l'appli reste utilisable, l'écran
    Paramètres reflète l'état réel via le battement de cœur, pas via cette valeur de retour)."""
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".xml")
        with os.fdopen(fd, "w", encoding="utf-16") as f:
            f.write(_task_xml())
        subprocess.run(
            ["schtasks", "/create", "/tn", TASK_NAME, "/xml", tmp_path, "/f"],
            check=True, capture_output=True, text=True,
        )
        logger.info(
            "Tâche planifiée '%s' enregistrée (connexion + relance auto toutes les %d min).",
            TASK_NAME, WATCHDOG_INTERVAL_MINUTES,
        )
        return True
    except subprocess.CalledProcessError as e:
        # str(e) seul ("returned non-zero exit status 1") ne dit jamais POURQUOI — le message
        # réel de schtasks.exe (ex : refus d'accès, XML invalide) n'est que dans stdout/stderr,
        # capturés par capture_output=True mais jamais journalisés jusqu'ici.
        detail = (e.stderr or e.stdout or "").strip()
        logger.error(
            "Échec de l'enregistrement de la tâche planifiée '%s' (code %s) : %s",
            TASK_NAME, e.returncode, detail or "(aucune sortie schtasks capturée)",
        )
        return False
    except Exception as e:
        logger.error("Échec de l'enregistrement de la tâche planifiée '%s' : %s", TASK_NAME, e)
        return False
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


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
