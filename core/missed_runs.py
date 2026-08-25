"""
DataScheduler — core/missed_runs.py
Détection des pipelines qui ont manqué leur exécution planifiée pendant que l'application était
fermée (chantier rattrapage au démarrage). État en mémoire, mono-processus — même patron que
core.pipeline._active_runs.

Le scheduler n'a pas de jobstore persistant (BackgroundScheduler sans jobstores=, voir
core/scheduler.py) : à chaque démarrage, init_scheduler() reconstruit tous les jobs à neuf, donc
une occurrence manquée pendant la fermeture n'existe jamais du point de vue d'APScheduler —
misfire_grace_time ne peut rien y rattraper. Ce module comble ça en lisant Pipeline.next_run_at
(persisté, laissé par la session précédente) AVANT que le scheduler ne le réécrive.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

_pending: dict[int, dict] = {}   # pipeline_id -> {pipeline_id, name, expected_at, late_minutes}


def detect_missed_runs(app_settings) -> list[dict]:
    """À appeler une seule fois au démarrage, en mode IN_APP, AVANT init_scheduler() — sans quoi
    next_run_at aurait déjà été recalculé vers la prochaine occurrence future et l'occurrence
    manquée serait perdue.

    Pipeline.next_run_at est un datetime naïf représentant l'heure murale dans le fuseau
    configuré de l'app (AppSettings.timezone — voir core/scheduler.py::__init__, qui passe ce
    même fuseau à BackgroundScheduler), jamais UTC ni l'heure du serveur : "maintenant" doit donc
    être calculé dans ce même fuseau puis dépouillé de son tzinfo pour rester comparable.

    Tolérance réutilisée telle quelle — AppSettings.misfire_grace_time_min, le même réglage
    "Tolérance de rattrapage" déjà affiché dans Paramètres, aucun nouveau réglage introduit.
    """
    from database import db_manager as db

    now = datetime.now(ZoneInfo(app_settings.timezone)).replace(tzinfo=None)
    tolerance_min = app_settings.misfire_grace_time_min

    _pending.clear()
    for p in db.get_pipelines(active_only=True):
        if not p.next_run_at or p.next_run_at >= now:
            continue
        late = now - p.next_run_at
        if late.total_seconds() / 60 > tolerance_min:
            continue   # trop ancien, hors tolérance — jamais proposé, comme aujourd'hui implicitement
        _pending[p.id] = {
            "pipeline_id": p.id,
            "name": p.name,
            "expected_at": p.next_run_at,
            "late_minutes": int(late.total_seconds() // 60),
        }
    return list(_pending.values())


def get_pending() -> list[dict]:
    return list(_pending.values())


def resolve(pipeline_id: int) -> None:
    """Retire un pipeline de la liste en attente — lancé ou ignoré explicitement. Jamais un
    simple masquage : une fois résolu, il ne réapparaît ni dans le dialogue de démarrage (déjà
    fermé) ni dans le bandeau du Dashboard au prochain refresh()."""
    _pending.pop(pipeline_id, None)
