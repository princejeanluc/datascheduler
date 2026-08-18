"""
DataScheduler — tests/test_settings_view.py
Chantier écran "Paramètres" : construction, navigation par catégorie, recherche à travers toutes
les catégories, sauvegarde des réglages de l'ordonnanceur/journalisation/interface. Les champs
de la catégorie Notifications (migrés depuis NotificationSettingsDialog) sont couverts dans
tests/test_dashboard_notifications.py, pas dupliqués ici.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _row(view, label_substr: str):
    return next(r for r in view._row_widgets if label_substr in r["label"])


def test_settings_view_constructs_without_error(qapp, test_db):
    from ui.main_window.settings_view import SettingsView

    view = SettingsView()
    assert len(view._row_widgets) > 0


def test_settings_view_prefills_from_app_settings(qapp, test_db):
    from ui.main_window.settings_view import SettingsView

    db.update_app_settings(
        timezone="Europe/Paris", misfire_grace_time_min=45, coalesce_missed_runs=False,
        max_concurrent_runs=10, log_level="DEBUG", dashboard_refresh_s=60,
    )
    view = SettingsView()

    assert view.cb_timezone.currentText() == "Europe/Paris"
    assert view.spin_misfire.value() == 45
    assert not view.chk_coalesce.isChecked()
    assert view.spin_max_concurrent.value() == 10
    assert view.cb_log_level.currentText() == "DEBUG"
    assert view.spin_dashboard_refresh.value() == 60


def test_select_category_shows_only_that_categorys_rows(qapp, test_db):
    from ui.main_window.settings_view import SettingsView

    view = SettingsView()
    view.select_category("logging")

    for row in view._row_widgets:
        assert row["wrapper"].isHidden() == (row["category"] != "logging")


def test_search_filters_across_all_categories(qapp, test_db):
    from ui.main_window.settings_view import SettingsView

    view = SettingsView()
    view.select_category("scheduler")

    view.inp_search.setText("rafraîchissement")   # ne matche que des lignes "interface"

    matched = [r for r in view._row_widgets if not r["wrapper"].isHidden()]
    assert matched   # au moins une correspondance
    assert all(r["category"] == "interface" for r in matched)

    view.inp_search.setText("")   # revient à la vue par catégorie (scheduler, la dernière active)
    for row in view._row_widgets:
        assert row["wrapper"].isHidden() == (row["category"] != "scheduler")


def test_search_shows_category_chip_only_while_searching(qapp, test_db):
    from ui.main_window.settings_view import SettingsView

    view = SettingsView()
    view.select_category("scheduler")
    for row in view._row_widgets:
        assert row["chip"].isHidden()   # jamais visible en navigation par catégorie

    view.inp_search.setText("fuseau")
    matched = _row(view, "fuseau horaire")
    assert not matched["chip"].isHidden()


def test_max_concurrent_runs_setting_saves_and_is_applied(qapp, test_db):
    """Depuis le chantier suivi des ressources, ce champ est réellement appliqué par
    run_pipeline() (tests/test_concurrency_cap.py) — ici on vérifie seulement que l'écran le
    sauvegarde correctement."""
    from ui.main_window.settings_view import SettingsView

    view = SettingsView()
    assert view.spin_max_concurrent is not None

    view.spin_max_concurrent.setValue(9)
    view._on_save()
    assert db.get_app_settings().max_concurrent_runs == 9


def test_resources_category_saves_sample_interval_and_retention(qapp, test_db):
    from ui.main_window.settings_view import SettingsView

    view = SettingsView()
    view.select_category("resources")
    for row in view._row_widgets:
        assert row["wrapper"].isHidden() == (row["category"] != "resources")

    view.spin_sample_interval.setValue(30)
    view.spin_sample_retention.setValue(3)
    view._on_save()

    settings = db.get_app_settings()
    assert settings.resource_sample_interval_s == 30
    assert settings.resource_sample_retention_days == 3


def test_resources_category_prefills_from_app_settings(qapp, test_db):
    from ui.main_window.settings_view import SettingsView

    db.update_app_settings(resource_sample_interval_s=120, resource_sample_retention_days=14)
    view = SettingsView()

    assert view.spin_sample_interval.value() == 120
    assert view.spin_sample_retention.value() == 14


def test_on_save_persists_scheduler_logging_and_interface_fields(qapp, test_db):
    from ui.main_window.settings_view import SettingsView

    view = SettingsView()
    view.cb_timezone.setCurrentIndex(view.cb_timezone.findText("Europe/Paris"))
    view.spin_misfire.setValue(20)
    view.chk_coalesce.setChecked(False)
    view.cb_log_level.setCurrentIndex(view.cb_log_level.findText("WARNING"))
    view.spin_log_mb.setValue(2)
    view.spin_log_backups.setValue(3)
    view.spin_dashboard_refresh.setValue(45)
    view.spin_pipelines_refresh.setValue(45)
    view.spin_live_log_refresh.setValue(5)
    view.spin_trace_glow_refresh.setValue(3)

    view._on_save()

    settings = db.get_app_settings()
    assert settings.timezone == "Europe/Paris"
    assert settings.misfire_grace_time_min == 20
    assert settings.coalesce_missed_runs is False
    assert settings.log_level == "WARNING"
    assert settings.log_max_bytes == 2_000_000
    assert settings.log_backup_count == 3
    assert settings.dashboard_refresh_s == 45
    assert settings.pipelines_refresh_s == 45
    assert settings.live_log_refresh_s == 5
    assert settings.trace_glow_refresh_s == 3


def test_execution_mode_row_present_and_prefills_default(qapp, test_db):
    from ui.main_window.settings_view import SettingsView

    view = SettingsView()
    assert view.cb_execution_mode is not None
    assert view.cb_execution_mode.currentData() == "IN_APP"
    assert view.lbl_worker_status.text() == "—"


def test_execution_mode_row_prefills_background(qapp, test_db):
    from ui.main_window.settings_view import SettingsView

    db.update_app_settings(execution_mode="BACKGROUND")
    view = SettingsView()

    assert view.cb_execution_mode.currentData() == "BACKGROUND"


def test_on_save_persists_execution_mode(qapp, test_db, monkeypatch):
    monkeypatch.setattr("core.task_scheduler.register_logon_task", lambda: True)

    from ui.main_window.settings_view import SettingsView
    view = SettingsView()
    idx = view.cb_execution_mode.findData("BACKGROUND")
    view.cb_execution_mode.setCurrentIndex(idx)
    view._on_save()

    assert db.get_app_settings().execution_mode == "BACKGROUND"


def test_on_save_switching_to_background_registers_logon_task(qapp, test_db, monkeypatch):
    calls = []
    monkeypatch.setattr("core.task_scheduler.register_logon_task", lambda: calls.append(True))

    from ui.main_window.settings_view import SettingsView
    view = SettingsView()
    idx = view.cb_execution_mode.findData("BACKGROUND")
    view.cb_execution_mode.setCurrentIndex(idx)
    view._on_save()

    assert calls == [True]


def test_on_save_switching_to_in_app_unregisters_task_and_enqueues_shutdown(qapp, test_db, monkeypatch):
    db.update_app_settings(execution_mode="BACKGROUND")
    calls = []
    monkeypatch.setattr("core.task_scheduler.unregister_logon_task", lambda: calls.append(True))

    from ui.main_window.settings_view import SettingsView
    view = SettingsView()
    idx = view.cb_execution_mode.findData("IN_APP")
    view.cb_execution_mode.setCurrentIndex(idx)
    view._on_save()

    assert calls == [True]
    pending = db.get_pending_worker_commands()
    assert any(c.command == "SHUTDOWN" for c in pending)


def test_on_save_without_mode_change_does_not_touch_logon_task(qapp, test_db, monkeypatch):
    """Rester en IN_APP (défaut) ne doit ni enregistrer ni désinscrire la tâche planifiée —
    seule une vraie transition de mode déclenche ces appels (voir _on_save())."""
    register_calls = []
    unregister_calls = []
    monkeypatch.setattr("core.task_scheduler.register_logon_task",
                         lambda: register_calls.append(True))
    monkeypatch.setattr("core.task_scheduler.unregister_logon_task",
                         lambda: unregister_calls.append(True))

    from ui.main_window.settings_view import SettingsView
    view = SettingsView()
    view._on_save()

    assert register_calls == []
    assert unregister_calls == []


def test_refresh_worker_status_shows_dash_in_app_mode(qapp, test_db):
    from ui.main_window.settings_view import SettingsView

    view = SettingsView()
    view._refresh_worker_status()
    assert view.lbl_worker_status.text() == "—"


def test_refresh_worker_status_shows_stopped_without_any_sample(qapp, test_db):
    from ui.main_window.settings_view import SettingsView

    db.update_app_settings(execution_mode="BACKGROUND")
    view = SettingsView()
    view._refresh_worker_status()
    assert "Arrêté" in view.lbl_worker_status.text()


def test_refresh_worker_status_shows_active_for_recent_sample(qapp, test_db):
    from datetime import datetime
    from database.models import ResourceSample
    from ui.main_window.settings_view import SettingsView

    db.update_app_settings(execution_mode="BACKGROUND")
    with db.get_session() as s:
        s.add(ResourceSample(timestamp=datetime.utcnow(), cpu_percent=1.0, memory_mb=10.0))

    view = SettingsView()
    view._refresh_worker_status()
    assert "Actif" in view.lbl_worker_status.text()


def test_refresh_worker_status_shows_stopped_for_stale_sample(qapp, test_db):
    from datetime import datetime, timedelta
    from database.models import ResourceSample
    from ui.main_window.settings_view import SettingsView

    db.update_app_settings(execution_mode="BACKGROUND", resource_sample_interval_s=10)
    with db.get_session() as s:
        s.add(ResourceSample(timestamp=datetime.utcnow() - timedelta(minutes=5),
                              cpu_percent=1.0, memory_mb=10.0))

    view = SettingsView()
    view._refresh_worker_status()
    assert "Arrêté" in view.lbl_worker_status.text()


def test_select_category_public_method_clears_search_first(qapp, test_db):
    """select_category() (utilisée par le raccourci 🔔 du Dashboard) doit toujours retomber sur
    la vue catégorie même si une recherche était en cours — sinon la recherche masquerait les
    lignes de la catégorie visée."""
    from ui.main_window.settings_view import SettingsView

    view = SettingsView()
    view.inp_search.setText("un texte qui ne correspond à rien du tout")

    view.select_category("logging")

    assert view.inp_search.text() == ""
    for row in view._row_widgets:
        assert row["wrapper"].isHidden() == (row["category"] != "logging")
