"""
DataScheduler — scripts/capture_views.py
Utilitaire dev (jamais exécuté par l'application) : produit une capture PNG de chaque vue
enregistrée, pour comparer visuellement à sa maquette dans une PR de la refonte (REGLES.md
section 6, point 3). Reprend le snippet de FONDATIONS.md section 5 (QT_QPA_PLATFORM=offscreen,
widget.grab().save(...), résolution 1440×900).

Registre volontairement incomplet au lot 0a : seules les vues instanciables dans leur état par
défaut, sans scénario applicatif particulier, y figurent. Chaque Lot A ajoute au registre les
états que sa fiche d'écran liste (survol, vide, validation...) au moment où ces états existent
réellement dans le code — jamais par anticipation.

Usage : python scripts/capture_views.py [dossier_de_sortie]
(dossier par défaut : docs/refonte/captures/)
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QDialog

from ui.fonts import register_app_fonts
from ui.main_window.widgets import GLOBAL_STYLE
from database import db_manager as db

# Largeur de la zone de contenu (1440 moins les 56px de la barre de navigation repliée, voir
# FONDATIONS.md section 5) × hauteur de fenêtre.
CAPTURE_WIDTH = 1440 - 56
CAPTURE_HEIGHT = 900


def _settings_view():
    from ui.main_window.settings_view import SettingsView
    return SettingsView()


def _settings_view_recherche():
    from ui.main_window.settings_view import SettingsView
    view = SettingsView()
    view.inp_search.setText("rafraîch")
    return view


def _settings_view_arriere_plan():
    from ui.main_window.settings_view import SettingsView
    view = SettingsView()
    idx = view.cb_execution_mode.findData("BACKGROUND")
    view.cb_execution_mode.setCurrentIndex(idx)
    return view


def _settings_view_refus():
    """register_logon_task() simulé en échec (politique IT) — même scénario que
    tests/test_settings_view.py::test_failure_banner_shown_when_background_registration_fails."""
    from unittest.mock import patch
    from ui.main_window.settings_view import SettingsView
    view = SettingsView()
    idx = view.cb_execution_mode.findData("BACKGROUND")
    view.cb_execution_mode.setCurrentIndex(idx)
    with patch("core.task_scheduler.register_logon_task", return_value=False):
        view._on_save()
    return view


def _settings_view_notifications_hebdomadaire():
    from ui.main_window.settings_view import SettingsView
    view = SettingsView()
    view.select_category("notifications")
    idx = view.cb_frequency.findData("WEEKLY")
    view.cb_frequency.setCurrentIndex(idx)
    return view


def _settings_view_enregistre():
    from ui.main_window.settings_view import SettingsView
    view = SettingsView()
    view._on_save()
    return view


def _resources_view_vide():
    from ui.main_window.resources_view import ResourcesView
    return ResourcesView()


def _seed_resource_samples(count: int, step_minutes: int):
    """Échantillons déterministes (pas de random — capture reproductible d'une exécution à
    l'autre), une ondulation simple pour que les graphiques ne soient pas des droites plates."""
    from datetime import datetime, timedelta
    from database.models import ResourceSample
    now = datetime.utcnow()
    with db.get_session() as s:
        for i in range(count):
            ts = now - timedelta(minutes=(count - i) * step_minutes)
            wave = abs((i % 20) - 10) / 10
            s.add(ResourceSample(
                timestamp=ts,
                cpu_percent=min(8.0 + 35.0 * wave, 95.0),
                memory_mb=180.0 + i * 1.2,
            ))


def _resources_view():
    from ui.main_window.resources_view import ResourcesView
    _seed_resource_samples(count=120, step_minutes=12)   # ~24h d'échantillons
    return ResourcesView()


def _resources_view_survol():
    view = _resources_view()
    view._on_chart_hover(60)
    return view


def _resources_view_7j():
    from ui.main_window.resources_view import ResourcesView
    _seed_resource_samples(count=168, step_minutes=60)   # un point par heure, 7 jours
    view = ResourcesView()
    view._on_range_changed(24 * 7)
    return view


def _dashboard_view():
    """Capturée avant toute création de pipeline dans le registre (ordre ci-dessous) : base
    encore vide -> état "Aujourdhui-premier" (A12)."""
    from ui.main_window.dashboard_view import DashboardView
    return DashboardView()


def _dashboard_seed_main_state():
    """Échec actif + pipeline manqué + run réussi du jour (Aujourdhui, critère d'acceptation :
    "avec un échec, un manqué et des runs du jour"). Pipelines dédiés à cette fabrique (noms
    "-capture"), jamais réutilisés par les fabriques suivantes — même principe d'indépendance que
    les fabriques ressources* (chacune ajoute ses propres échantillons)."""
    from datetime import datetime, timedelta
    from database.models import Pipeline
    from core import missed_runs

    failing = db.create_pipeline(name="export-ventes-quotidien")
    db.save_steps(failing.id, [{
        "step_type": "DB_EXTRACT", "label": "Extraire les ventes",
        "config": {"_step_key": "step-1"}, "retry_count": 2,
    }])
    run = db.create_run(failing.id)
    db.finish_run(run.id, "FAILED", error_message="ORA-12541: TNS:no listener",
                   failed_step_key="step-1")
    with db.get_session() as s:
        s.get(Pipeline, failing.id).last_status = "FAILED"

    missed_pipeline = db.create_pipeline(name="synchro-stock-matinale")
    missed_runs._pending[missed_pipeline.id] = {
        "pipeline_id": missed_pipeline.id, "name": missed_pipeline.name,
        "expected_at": datetime.utcnow() - timedelta(hours=3), "late_minutes": 180,
    }

    healthy = db.create_pipeline(name="depot-rapport-mensuel")
    ok_run = db.create_run(healthy.id)
    db.finish_run(ok_run.id, "SUCCESS")
    with db.get_session() as s:
        s.get(Pipeline, healthy.id).last_status = "SUCCESS"


def _dashboard_view_avec_donnees():
    from ui.main_window.dashboard_view import DashboardView
    _dashboard_seed_main_state()
    return DashboardView()


def _settle_side_panel(view):
    """Même technique que tests/test_side_panel.py (voir son historique) : saute à la fin de
    l'animation de glissement plutôt que d'attendre en temps réel, pour une capture déterministe
    du panneau déjà ouvert plutôt que mi-course."""
    app = QApplication.instance()
    view._side_panel._anim.setCurrentTime(view._side_panel._anim.duration())
    app.processEvents()


def _dashboard_view_execution():
    """A9 : panneau latéral d'une exécution en échec (Aujourdhui-execution)."""
    from database.models import Pipeline
    from ui.main_window.dashboard_view import DashboardView

    pipeline = db.create_pipeline(name="export-devises-capture")
    db.save_steps(pipeline.id, [{
        "step_type": "DB_EXTRACT", "label": "Extraire les taux",
        "config": {"_step_key": "step-1"}, "retry_count": 1,
    }])
    run = db.create_run(pipeline.id)
    db.finish_run(run.id, "FAILED", error_message="ConnectionError: délai dépassé (30s)",
                   failed_step_key="step-1")
    with db.get_session() as s:
        s.get(Pipeline, pipeline.id).last_status = "FAILED"

    view = DashboardView()
    view.resize(CAPTURE_WIDTH, CAPTURE_HEIGHT)
    view.show()
    QApplication.instance().processEvents()
    view._open_failure_panel(pipeline.id)
    _settle_side_panel(view)
    return view


def _dashboard_view_encours():
    """A10 : panneau latéral d'une exécution en cours (Aujourdhui-encours). `_active_runs` posé
    avant la construction de la vue, pour que le rail MAINTENANT la reflète aussi (même ordre que
    tests/test_dashboard_treat_column.py::test_open_running_panel_populates_and_opens_side_panel),
    retiré en sortie de fabrique pour ne pas fausser les fabriques suivantes qui construisent
    elles aussi une DashboardView."""
    import threading
    import core.pipeline as pipeline_module
    from ui.main_window.dashboard_view import DashboardView

    pipeline = db.create_pipeline(name="synchro-stock-capture")
    run = db.create_run(pipeline.id)
    db.update_run_progress(
        run.id, "Étape 2/4 : Appeler l'API", "14:04:23 Démarrage requête…", "step-2",
    )

    pipeline_module._active_runs[pipeline.id] = threading.Event()
    try:
        view = DashboardView()
        view.resize(CAPTURE_WIDTH, CAPTURE_HEIGHT)
        view.show()
        QApplication.instance().processEvents()
        view._open_running_panel(pipeline.id)
        _settle_side_panel(view)
    finally:
        pipeline_module._active_runs.pop(pipeline.id, None)
    return view


def _dashboard_view_tout():
    """Fenêtre flottante de confirmation de "Tout exécuter" (Aujourdhui-tout) : reconstruite
    directement (même contenu que le QMessageBox.question() de _on_run_all), jamais via .exec()
    qui bloquerait ce script — QMessageBox est un QDialog, capture_all() ne force donc pas sa
    taille à 1440x900 (voir le test isinstance), même traitement que la fenêtre de rattrapage."""
    from PySide6.QtWidgets import QMessageBox
    return QMessageBox(
        QMessageBox.Question, "Tout exécuter",
        "Lancer 3 pipeline(s) actif(s) maintenant ?",
        QMessageBox.Yes | QMessageBox.No,
    )


def _dashboard_view_rattrapage():
    """Fenêtre de rattrapage au démarrage (Aujourdhui-rattrapage), A11 — QDialog construit
    directement avec une liste de pipelines manqués, jamais via .exec() (bloquerait ce script).
    Indépendante de la base (liste littérale), donc insensible à l'ordre du registre."""
    from datetime import datetime, timedelta
    from ui.dialogs.missed_pipelines_dialog import MissedPipelinesDialog

    missed = [
        {"pipeline_id": 1, "name": "export-ventes-quotidien",
         "expected_at": datetime.utcnow() - timedelta(hours=3), "late_minutes": 180},
        {"pipeline_id": 2, "name": "synchro-stock-matinale",
         "expected_at": datetime.utcnow() - timedelta(hours=1), "late_minutes": 60},
    ]
    return MissedPipelinesDialog(None, missed)


# (nom de fichier sans extension, fabrique de la vue) — un enregistrement par vue/état capturable.
# Parametres-validation n'est pas capturé : son contenu distinctif (bandeau de validation en
# ligne par champ) est C3, gated par la décision P1 — voir docs/refonte/impact/a-parametres.md.
# Ressources-plage n'est pas capturé non plus : glisser pour choisir une plage est C2, gated —
# voir docs/refonte/impact/a-ressources.md.
REGISTRY = [
    ("parametres", _settings_view),
    ("parametres-recherche", _settings_view_recherche),
    ("parametres-arriere-plan", _settings_view_arriere_plan),
    ("parametres-refus", _settings_view_refus),
    ("parametres-notifications", _settings_view_notifications_hebdomadaire),
    ("parametres-enregistre", _settings_view_enregistre),
    # Ordre important : capture_all() partage une seule base pour tout le registre, et chaque
    # fabrique "ressources*" y ajoute ses propres échantillons — "-vide" doit passer avant que
    # quoi que ce soit n'en insère, "-7j" avant les échantillons plus denses de "ressources"/
    # "-survol" (sinon les deux séries se superposent dans la même fenêtre 7j).
    ("ressources-vide", _resources_view_vide),
    ("ressources-7j", _resources_view_7j),
    ("ressources", _resources_view),
    ("ressources-survol", _resources_view_survol),
    # "aujourdhui-premier" doit passer avant toute création de pipeline dans ce registre (base
    # encore vide à ce moment -> état A12), "aujourdhui" ajoute ensuite les siens.
    ("aujourdhui-premier", _dashboard_view),
    ("aujourdhui", _dashboard_view_avec_donnees),
    ("aujourdhui-execution", _dashboard_view_execution),
    ("aujourdhui-encours", _dashboard_view_encours),
    ("aujourdhui-tout", _dashboard_view_tout),
    ("aujourdhui-rattrapage", _dashboard_view_rattrapage),
]


def _init_disposable_db():
    """Base SQLite jetable dans un dossier temporaire — jamais la vraie base applicative (même
    règle que tests/conftest.py::test_db)."""
    db_path = Path(tempfile.mkdtemp(prefix="kulu_capture_")) / "capture.db"
    db.init_db(db_path)


def capture_all(out_dir: Path) -> list[Path]:
    """Suppose qu'une base (jetable ou non) est déjà initialisée via db.init_db() — jamais
    appelé ici, pour rester réutilisable depuis un test qui a déjà sa propre base jetable
    (fixture test_db)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    register_app_fonts()
    app.setStyleSheet(GLOBAL_STYLE)

    produced = []
    for name, build_view in REGISTRY:
        view = build_view()
        # Aujourdhui-tout/-rattrapage (QMessageBox/QDialog, jamais des vues plein écran) :
        # forcer 1440x900 laisserait une grande zone vide autour d'une fenêtre flottante conçue
        # pour sa taille naturelle (REGLES.md section 6, point 3 — reste une capture "propre").
        if not isinstance(view, QDialog):
            view.resize(CAPTURE_WIDTH, CAPTURE_HEIGHT)
        view.show()
        app.processEvents()
        # show() sur une fenêtre top-level sans parent donne le focus clavier au premier widget
        # focusable (le champ de recherche, premier ajouté au rail) dès que rien d'autre ne l'a
        # déjà pris — un artefact du script, pas l'état par défaut réel (dans l'app, la vue est
        # intégrée à une fenêtre déjà active, ce changement de focus n'a pas lieu). Sans ce
        # nettoyage, la capture montrait à tort une bordure de focus (accent) sur le champ de
        # recherche même sur les états qui ne simulent aucune saisie utilisateur. Seule la
        # capture "recherche" doit garder ce focus (une recherche en cours a le curseur dedans,
        # Parametres-recherche.html).
        search_box = getattr(view, "inp_search", None)
        if search_box is not None and name != "parametres-recherche":
            search_box.clearFocus()
            app.processEvents()
        out_path = out_dir / f"{name}.png"
        view.grab().save(str(out_path))
        produced.append(out_path)
    return produced


if __name__ == "__main__":
    _init_disposable_db()
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "refonte" / "captures"
    for path in capture_all(out_dir):
        print(path)
