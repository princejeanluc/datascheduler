"""
DataScheduler — core/execution_mode.py
Point de décision unique "cette action doit-elle s'exécuter localement, ou être déléguée au
worker en arrière-plan ?" (chantier exécution en arrière-plan). Centralise la lecture
d'AppSettings.execution_mode pour que chaque appelant (PipelinesView, PipelineSettingsDialog,
SettingsView…) n'ait pas à connaître le détail du canal de coordination (WorkerCommand).
"""


def is_background_mode_active() -> bool:
    from database import db_manager as db
    return db.get_app_settings().execution_mode == "BACKGROUND"


def request_run_now(pipeline_id: int) -> bool:
    """Délègue le lancement au worker si le mode arrière-plan est actif. Retourne True si
    délégué (l'appelant ne doit RIEN exécuter localement), False si le mode est IN_APP (l'appelant
    garde son comportement local habituel)."""
    from database import db_manager as db
    if not is_background_mode_active():
        return False
    db.enqueue_worker_command("RUN_NOW", {"pipeline_id": pipeline_id})
    return True


def request_reload() -> bool:
    """Signale au worker qu'un pipeline ou un réglage a changé et doit être repris en compte
    (nouveau pipeline, activation/désactivation, modification de planification, changement de
    Paramètres). Même contrat de retour que request_run_now()."""
    from database import db_manager as db
    if not is_background_mode_active():
        return False
    db.enqueue_worker_command("RELOAD")
    return True


def request_cancel_run(pipeline_id: int) -> bool:
    """Demande l'interruption coopérative d'un run en cours, déléguée au worker. Nécessaire en
    plus de request_run_now() : core.pipeline._active_runs (ce que request_cancel() de
    core/pipeline.py manipule) est un état EN MÉMOIRE, propre au process qui exécute réellement
    le pipeline — en mode arrière-plan, c'est le worker, jamais l'appli desktop, donc appeler
    request_cancel() localement depuis l'appli n'aurait aucun effet. Même contrat de retour que
    les fonctions ci-dessus."""
    from database import db_manager as db
    if not is_background_mode_active():
        return False
    db.enqueue_worker_command("CANCEL", {"pipeline_id": pipeline_id})
    return True


def is_pipeline_running_anywhere(pipeline_id: int) -> bool:
    """État "en cours" fiable quel que soit le process qui exécute réellement le pipeline —
    contrairement à core.pipeline.is_pipeline_running() (mémoire, propre au process), lit
    Pipeline.last_status en base, écrit par _update_pipeline_status() indépendamment de qui
    exécute. À utiliser côté UI dès que le mode arrière-plan peut être actif."""
    from database import db_manager as db
    p = db.get_pipeline(pipeline_id)
    if not p:
        return False
    status = p.last_status
    status_str = status.value if hasattr(status, "value") else str(status or "IDLE")
    return status_str == "RUNNING"
