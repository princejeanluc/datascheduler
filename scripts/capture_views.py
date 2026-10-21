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

from PySide6.QtWidgets import QApplication, QDialog, QMenu, QPushButton, QLabel

from ui.fonts import register_app_fonts
from ui.main_window.widgets import GLOBAL_STYLE
from ui.components import Bubble
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


def _pipelines_view_vide():
    """A14 : état vide en trois cartes (Pipelines-vide) — capturée avant toute création de
    pipeline dans ce registre (base encore vide à ce moment), comme aujourdhui-premier."""
    from ui.main_window.pipelines_view import PipelinesView
    return PipelinesView()


def _pipelines_view():
    """Pipelines : un échec reprenable, un enfant (déclenchement), un en cours, un manqué, un
    inactif — critère d'acceptation de la fiche."""
    from datetime import datetime, timedelta
    from database.models import Pipeline, PipelineRun
    from ui.main_window.pipelines_view import PipelinesView

    parent = db.create_pipeline(
        name="synchro-clients-crm", description="Oracle CRM -> référentiel clients",
        frequency="DAILY", scheduled_time="07:00",
    )
    db.save_steps(parent.id, [{
        "step_type": "DB_EXTRACT", "label": "Extraire clients",
        "config": {"_step_key": "step-1"}, "retry_count": 2,
    }])
    run = db.create_run(parent.id)
    db.finish_run(run.id, "FAILED", error_message="ORA-12541: TNS:no listener", failed_step_key="step-1")
    with db.get_session() as s:
        s.get(PipelineRun, run.id).resumable_state_json = "{}"   # reprenable
        s.get(Pipeline, parent.id).last_status = "FAILED"

    child = db.create_pipeline(
        name="export-hive-oracle", description="Agrégats Hive vers l'entrepôt",
        frequency="DAILY", scheduled_time="08:00",
    )
    db.save_steps(child.id, [{"step_type": "SPARK_SQL"}, {"step_type": "DB_EXECUTE"}])
    db.set_pipeline_trigger(child.id, parent.id, "SUCCESS")

    running = db.create_pipeline(name="appel-api-facturation", description="Factures du jour vers le partage")
    db.save_steps(running.id, [{"step_type": "HTTP_REQUEST"}, {"step_type": "LOCAL_COPY"}])
    running_run = db.create_run(running.id)
    with db.get_session() as s:
        s.get(PipelineRun, running_run.id).started_at = datetime.utcnow() - timedelta(seconds=42)
        s.get(Pipeline, running.id).last_status = "RUNNING"
    db.update_run_progress(running_run.id, "Étape 2/4 : Appeler l'API", "log", "step-2")
    import core.pipeline as pipeline_module
    import threading
    pipeline_module._active_runs[running.id] = threading.Event()

    missed = db.create_pipeline(name="purge-fichiers-temporaires", description="Nettoie C:\\Kulu\\tmp")
    from core import missed_runs
    missed_runs._pending[missed.id] = {
        "pipeline_id": missed.id, "name": missed.name,
        "expected_at": datetime.utcnow() - timedelta(hours=3), "late_minutes": 180,
    }

    inactive = db.create_pipeline(name="controle-ventes-mensuel", description="Écarts ventes / facturation")
    db.set_pipeline_active(inactive.id, False)

    view = PipelinesView()
    view.resize(CAPTURE_WIDTH, CAPTURE_HEIGHT)
    view.show()
    QApplication.instance().processEvents()
    view.refresh()
    # Retiré après refresh() (déjà reflété dans les widgets construits) — ne doit pas fausser
    # is_pipeline_running() pour les fabriques suivantes du même registre (même précaution que
    # dashboard_view_encours plus haut).
    pipeline_module._active_runs.pop(running.id, None)
    return view


def _pipelines_view_menu():
    """Pipelines-menu : le menu "⋯" capturé seul (jamais composité avec la vue derrière — même
    traitement que Aujourdhui-tout/-rattrapage, ce sont des popups indépendants du point de vue
    de Qt, invisibles dans le grab() du widget parent)."""
    from database.models import Pipeline
    from ui.main_window.pipelines_view import PipelinesView

    pipeline = db.create_pipeline(name="synchro-clients-crm-menu", description="Oracle CRM -> référentiel clients")
    db.save_steps(pipeline.id, [{
        "step_type": "DB_EXTRACT", "label": "Extraire clients",
        "config": {"_step_key": "step-1"}, "retry_count": 2,
    }])
    run = db.create_run(pipeline.id)
    db.finish_run(run.id, "FAILED", error_message="ORA-12541: TNS:no listener", failed_step_key="step-1")
    with db.get_session() as s:
        s.get(Pipeline, pipeline.id).last_status = "FAILED"

    view = PipelinesView()
    view.resize(CAPTURE_WIDTH, CAPTURE_HEIGHT)
    view.show()
    app = QApplication.instance()
    app.processEvents()
    view.refresh()

    # La base est partagée avec les fabriques précédentes du registre (ex. "pipelines" a déjà
    # ajouté 5 lignes) — retrouve la bonne ligne par nom, jamais une position fixe.
    row = next(
        r for r in range(view.table.rowCount())
        if "synchro-clients-crm-menu" in view.table.cellWidget(r, 0).findChildren(QLabel)[0].text()
    )
    cell = view.table.cellWidget(row, 5)
    btn_more = next(b for b in cell.findChildren(QPushButton) if b.menu() is not None)
    menu = btn_more.menu()
    menu.popup(btn_more.mapToGlobal(btn_more.rect().bottomRight()))
    app.processEvents()
    return menu


def _pipelines_view_validation():
    """Pipelines-validation : panneau latéral de validation à blanc (A10), réutilise SidePanel."""
    from ui.main_window.pipelines_view import PipelinesView

    pipeline = db.create_pipeline(name="synchro-clients-crm-validation")
    # Pas d'étape : dry_run_pipeline() échoue tout de suite sur la forme, sans test réseau réel
    # (rapide et déterministe pour une capture).

    view = PipelinesView()
    view.resize(CAPTURE_WIDTH, CAPTURE_HEIGHT)
    view.show()
    QApplication.instance().processEvents()
    view._on_validate_pipeline(pipeline.id, pipeline.name)
    view._validation_thread.wait(5000)
    QApplication.instance().processEvents()
    _settle_side_panel(view)
    return view


def _pipelines_view_suppression():
    """Pipelines-suppression : fenêtre de suppression modale (A13), capturée seule — même
    traitement que Aujourdhui-rattrapage (QDialog construit directement, jamais via .exec())."""
    from ui.dialogs import PipelineDeleteDialog

    parent = db.create_pipeline(
        name="synchro-clients-crm-suppr", frequency="DAILY", scheduled_time="07:00",
    )
    child1 = db.create_pipeline(name="export-hive-oracle-suppr", frequency="DAILY", scheduled_time="08:00")
    db.set_pipeline_trigger(child1.id, parent.id, "FAILURE")
    child2 = db.create_pipeline(name="reporting-ventes-j1-suppr", frequency="DAILY", scheduled_time="06:00")
    db.set_pipeline_trigger(child2.id, parent.id, "SUCCESS")
    for _ in range(52):
        run = db.create_run(parent.id)
        db.finish_run(run.id, "SUCCESS")

    dependents = db.get_pipelines_triggered_by(parent.id)
    return PipelineDeleteDialog(None, parent, dependents, db.count_runs(parent.id))


def _connections_view():
    """Connexions : les 7 types de profils, avec un échec, un jamais testé, un lien de bastion
    SSH (A4) et une estompe « à retester » (A5) — critère d'acceptation de la fiche."""
    from datetime import datetime, timedelta
    from database.models import OracleProfile
    from ui.main_window.connections_view import ConnectionsView

    ora = db.create_oracle_profile(
        name="Oracle CRM_PROD", host="crm-db01.interne", port=1521, service_name="CRMP",
        username="svc_kulu", password="pw",
    )
    db.record_profile_test_result("oracle", ora.id, False)
    with db.get_session() as s:
        s.get(OracleProfile, ora.id).last_tested_at = datetime.utcnow()

    ref = db.create_database_profile(
        name="Postgres REF", db_type="POSTGRESQL", host="ref.interne", port=5432,
        username="etl_writer", password="pw", database_name="referentiel",
    )
    db.record_profile_test_result("database", ref.id, True)
    with db.get_session() as s:
        from database.models import DatabaseProfile
        s.get(DatabaseProfile, ref.id).last_tested_at = datetime.utcnow() - timedelta(days=41)

    sftp = db.create_ftp_profile(
        name="SFTP Partenaire", host="sftp.partner.fr", port=22, protocol="SFTP",
        username="kulu_partner", password="pw",
    )   # jamais testé — délibérément sans record_profile_test_result

    db.create_smtp_profile(
        name="SMTP Interne", host="smtp.interne", port=587, use_tls=True,
        from_address="kulu@entreprise.fr",
    )

    bastion = db.create_ssh_profile(
        name="Bastion DMZ", host="bastion.dmz", port=22, username="kulu", password="pw",
    )
    db.record_profile_test_result("ssh", bastion.id, True)
    edge = db.create_ssh_profile(
        name="Edge Hadoop", host="edge01.hadoop", port=22, username="kulu", password="pw",
        jump_via_id=bastion.id,
    )
    db.record_profile_test_result("ssh", edge.id, True)

    db.create_kerberos_profile(name="Kerberos KULU@HADOOP", principal="kulu@HADOOP.INTERNE", password="pw")
    db.create_elevation_profile(name="sudo hdfs", target_user="hdfs", password="pw")

    view = ConnectionsView()
    view.resize(CAPTURE_WIDTH, CAPTURE_HEIGHT)
    view.show()
    QApplication.instance().processEvents()
    view.refresh()
    return view


def _connections_view_formulaire():
    """Connexions-formulaire : modification d'un profil FTP avec le bandeau d'échec affiché."""
    from ui.dialogs import FtpDialog

    p = db.create_ftp_profile(
        name="SFTP Partenaire-form", host="sftp.partner.fr", port=22, protocol="SFTP",
        username="kulu_partner", password="pw",
    )
    dlg = FtpDialog(None, profile=p)
    dlg._on_test_result(False, "Authentication failed for user kulu_partner")
    return dlg


def _connections_view_sante():
    """Connexions-sante : bilan de santé avec un échec, une réussite et un Kerberos "non
    testable ici" (A10)."""
    from ui.dialogs import ConnectionHealthDialog

    ora = db.create_oracle_profile(
        name="Oracle CRM_PROD-sante", host="crm-db01.interne", port=1521, service_name="CRMP",
        username="svc_kulu", password="pw",
    )
    db.create_ftp_profile(
        name="Partage ventes-sante", host="ftp.interne", port=990, protocol="FTPS",
        username="kulu", password="pw",
    )
    db.create_kerberos_profile(name="Kerberos KULU@HADOOP-sante", principal="kulu@HADOOP.INTERNE", password="pw")

    dlg = ConnectionHealthDialog(None)
    row_ora = next(i for i, r in enumerate(dlg._rows) if r["id"] == ora.id)
    dlg._on_row_tested(row_ora, False, "ORA-12541: TNS:no listener")
    return dlg


def _connections_view_suppression():
    """Connexions-suppression : confirmation de suppression d'un SSH utilisé comme bastion,
    avec un pipeline dépendant (A11)."""
    from ui.dialogs import ConnectionDeleteDialog

    pipeline = db.create_pipeline(name="depot-partenaire-hebdo-suppr")
    return ConnectionDeleteDialog(
        None, "SFTP", "SFTP Partenaire-suppr",
        used_by=[pipeline.name], bastion_users=["Edge Hadoop-suppr"],
    )


def _queries_view():
    """Requêtes SQL : quelques requêtes dans la bibliothèque, une sélectionnée avec mots-clés,
    fonction et jeton visibles dans l'éditeur (A3, A6, A7, A8)."""
    from ui.main_window.queries_view import QueriesView

    extraction = db.create_sql_query(
        name="EXTRAIRE_VENTES_J1",
        description="Ventes de la veille, par magasin",
        sql_text=(
            "SELECT\n"
            "  v.magasin_id,\n"
            "  v.montant_ttc\n"
            "FROM ventes v\n"
            "WHERE v.date_vente = TO_DATE('{expr:fmt(date_add(today(), -1), \"{yyyy}-{MM}-{dd}\")}', "
            "'YYYY-MM-DD')"
        ),
    )
    db.create_sql_query(name="PURGE_TEMP_STAGING", sql_text="DELETE FROM temp_staging WHERE 1=1")
    db.create_sql_query(name="MAJ_REFERENTIEL_CLIENTS", sql_text="UPDATE ref SET actif = 1")

    pipeline = db.create_pipeline(name="reporting-ventes-j1-capture")
    db.save_steps(pipeline.id, [{
        "step_type": "DB_EXTRACT", "label": "Extraire ventes J-1",
        "config": {"_step_key": "step-1", "sql_query_id": extraction.id},
    }])

    view = QueriesView()
    view.resize(CAPTURE_WIDTH, CAPTURE_HEIGHT)
    view.show()
    QApplication.instance().processEvents()
    view._select_query(extraction.id)
    return view


def _queries_view_rechercher():
    """SQL-rechercher : 3 occurrences de v.date_vente, barre ouverte sur la 2e (compteur 2/3,
    A9)."""
    from ui.main_window.queries_view import QueriesView

    q = db.create_sql_query(
        name="EXTRAIRE_RETOURS_J1-rechercher",
        sql_text=(
            "SELECT r.numero_retour\n"
            "FROM retours r\n"
            "JOIN ventes v ON v.id = r.vente_id\n"
            "WHERE v.date_vente = TO_DATE('{yyyy}-{MM}-{dd}', 'YYYY-MM-DD')\n"
            "  AND v.date_vente < SYSDATE\n"
            "ORDER BY v.date_vente"
        ),
    )

    view = QueriesView()
    view.resize(CAPTURE_WIDTH, CAPTURE_HEIGHT)
    view.show()
    QApplication.instance().processEvents()
    view._select_query(q.id)
    view.editor.show_find_bar()
    view.editor._find_bar.inp_find.setText("v.date_vente")
    view.editor._find_bar.step(1)   # passe de 1/3 à 2/3
    QApplication.instance().processEvents()
    return view


def _queries_view_depuis_etape():
    """SQL-depuis-etape : modale de création ouverte depuis une étape, surtitre contextuel
    (A10)."""
    from ui.dialogs import SqlQueryDialog

    dlg = SqlQueryDialog(step_label="Extraire les retours",
                         pipeline_name="Reporting ventes J-1")
    dlg.show()
    QApplication.instance().processEvents()
    # Ce état ne simule aucune saisie en cours — sans ceci, le champ Nom (premier widget
    # focusable) affiche à tort une bordure de focus accent (REGLES.md section 6, point 3).
    dlg.inp_name.clearFocus()
    QApplication.instance().processEvents()
    return dlg


def _history_backdate_run(run_id: int, days_ago: int, duration_seconds: int = 180):
    """db.finish_run() date toujours avec datetime.utcnow() — appelé APRÈS, pour replacer un run
    dans un groupe de jour plus ancien (A5 : AUJOURD'HUI/HIER/date) sans dupliquer sa logique de
    statut/compteurs."""
    from datetime import datetime, timedelta
    from database.models import PipelineRun
    with db.get_session() as s:
        r = s.get(PipelineRun, run_id)
        r.finished_at = datetime.utcnow() - timedelta(days=days_ago)
        r.started_at = r.finished_at - timedelta(seconds=duration_seconds)


def _history_view():
    """Historique : runs répartis sur aujourd'hui/hier/plus ancien (groupes de jours, A5), un
    échec reprenable (bouton "Reprendre depuis l'échec" dans le tableau, A8), calendrier de
    fréquence à 4 niveaux alimenté sur plusieurs jours (A4)."""
    from ui.main_window.history_view import HistoryView

    p = db.create_pipeline(
        name="synchro-clients-crm-hist", description="Oracle CRM -> référentiel clients",
        frequency="DAILY", scheduled_time="07:00",
    )
    db.save_steps(p.id, [{
        "step_type": "DB_EXTRACT", "label": "Extraire clients", "config": {"_step_key": "step-1"},
    }])

    run_today = db.create_run(p.id)
    db.finish_run(run_today.id, "SUCCESS", rows_exported=18234)

    run_fail = db.create_run(p.id)
    db.finish_run(
        run_fail.id, "FAILED", error_message="ORA-12541: TNS:no listener", failed_step_key="step-1")
    from database.models import PipelineRun
    with db.get_session() as s:
        s.get(PipelineRun, run_fail.id).resumable_state_json = "{}"

    run_yesterday = db.create_run(p.id)
    db.finish_run(run_yesterday.id, "SUCCESS", rows_exported=9000)
    _history_backdate_run(run_yesterday.id, days_ago=1, duration_seconds=240)

    run_old = db.create_run(p.id)
    db.finish_run(run_old.id, "CANCELLED")
    _history_backdate_run(run_old.id, days_ago=5, duration_seconds=38)

    # Alimente le calendrier de fréquence (90 jours, 4 niveaux : bg_card/success_dim/success/
    # danger) avec un peu d'historique au-delà des groupes de jours ci-dessus.
    for i in range(10):
        r = db.create_run(p.id)
        db.finish_run(r.id, "FAILED" if i % 4 == 0 else "SUCCESS")
        _history_backdate_run(r.id, days_ago=i + 10)

    view = HistoryView()
    view.resize(CAPTURE_WIDTH, CAPTURE_HEIGHT)
    view.show()
    QApplication.instance().processEvents()
    view.refresh()
    return view


def _history_view_jour():
    """Historique-jour : bulle du jour (A9), capturée seule — même traitement que Pipelines-menu
    (popup indépendant du point de vue de Qt, invisible dans le grab() de la vue derrière)."""
    from datetime import date
    from ui.main_window.history_view import HistoryView

    p = db.create_pipeline(name="synchro-clients-crm-jour")
    r1 = db.create_run(p.id)
    db.finish_run(r1.id, "SUCCESS", rows_exported=18234)
    r2 = db.create_run(p.id)
    db.finish_run(r2.id, "FAILED", error_message="ORA-12541: TNS:no listener")

    view = HistoryView()
    view.resize(CAPTURE_WIDTH, CAPTURE_HEIGHT)
    view.show()
    QApplication.instance().processEvents()
    view._on_frequency_day_clicked(p, date.today())
    QApplication.instance().processEvents()
    return view._bubble


def _history_view_run():
    """Historique-run : panneau latéral d'un run en échec reprenable (A10, SidePanel)."""
    from ui.main_window.history_view import HistoryView

    p = db.create_pipeline(name="synchro-clients-crm-run")
    db.save_steps(p.id, [{
        "step_type": "DB_EXTRACT", "label": "Extraire clients", "config": {"_step_key": "step-1"},
    }])
    run = db.create_run(p.id)
    db.finish_run(
        run.id, "FAILED", error_message="ORA-12541: TNS:no listener", failed_step_key="step-1",
        resumable_state_json="{}",
        log_text="[07:00:01] Démarrage\n[07:00:04] ORA-12541: TNS:no listener",
    )

    view = HistoryView()
    view.resize(CAPTURE_WIDTH, CAPTURE_HEIGHT)
    view.show()
    QApplication.instance().processEvents()
    view._open_run_panel(run.id)
    QApplication.instance().processEvents()
    return view


def _history_view_modifications():
    """Historique-modifications : second onglet "Journal des modifications" (A11/A12)."""
    from ui.main_window.history_view import HistoryView

    db.log_audit_event(
        "pipeline_created", pipeline_id=1, pipeline_name="synchro-clients-crm-mod")
    db.log_audit_event(
        "pipeline_edited", pipeline_id=1, pipeline_name="synchro-clients-crm-mod",
        detail="Nom/description/planification",
    )
    db.log_audit_event(
        "pipeline_imported", pipeline_id=2, pipeline_name="export-hive-oracle-mod",
        detail="action=overwrite",
    )
    db.log_audit_event("pipeline_deleted", pipeline_name="controle-ventes-mensuel-mod")

    view = HistoryView()
    view.resize(CAPTURE_WIDTH, CAPTURE_HEIGHT)
    view.show()
    QApplication.instance().processEvents()
    view.refresh()
    view._set_active_tab(1)
    QApplication.instance().processEvents()
    return view


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
    # "pipelines-vide" et "aujourdhui-premier" doivent tous deux passer avant la moindre création
    # de pipeline dans ce registre (base encore vide à ce moment) — groupés ici avant toute
    # fabrique qui en crée, peu importe l'ordre relatif entre les deux (aucun des deux n'en crée).
    ("pipelines-vide", _pipelines_view_vide),
    ("aujourdhui-premier", _dashboard_view),
    ("pipelines", _pipelines_view),
    ("pipelines-menu", _pipelines_view_menu),
    ("pipelines-validation", _pipelines_view_validation),
    ("pipelines-suppression", _pipelines_view_suppression),
    ("aujourdhui", _dashboard_view_avec_donnees),
    ("aujourdhui-execution", _dashboard_view_execution),
    ("aujourdhui-encours", _dashboard_view_encours),
    ("aujourdhui-tout", _dashboard_view_tout),
    ("aujourdhui-rattrapage", _dashboard_view_rattrapage),
    # Historique-pipeline n'est pas capturé : le bandeau qui le remplacerait un jour est C9,
    # gated (dépend de B5/C8) — voir docs/refonte/impact/a-historique.md.
    ("historique", _history_view),
    ("historique-jour", _history_view_jour),
    ("historique-run", _history_view_run),
    ("historique-modifications", _history_view_modifications),
    # Connexions-nouvelle/-detail non capturés : C4/C6, entièrement gated — voir
    # docs/refonte/impact/a-connexions.md.
    ("connexions", _connections_view),
    ("connexions-formulaire", _connections_view_formulaire),
    ("connexions-sante", _connections_view_sante),
    ("connexions-suppression", _connections_view_suppression),
    # SQL-apercu/-jetons/-resolu/-enregistrer non capturés : entièrement Lot C (C1, C4, C3, C5),
    # gated — voir docs/refonte/impact/a-requetes-sql.md.
    ("sql", _queries_view),
    ("sql-rechercher", _queries_view_rechercher),
    ("sql-depuis-etape", _queries_view_depuis_etape),
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
        # Aujourdhui-tout/-rattrapage/Pipelines-suppression (QMessageBox/QDialog) et
        # Pipelines-menu (QMenu) : jamais des vues plein écran — forcer 1440x900 laisserait une
        # grande zone vide autour d'une fenêtre/d'un popup flottant conçu pour sa taille
        # naturelle (REGLES.md section 6, point 3 — reste une capture "propre").
        if not isinstance(view, (QDialog, QMenu, Bubble)):
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
