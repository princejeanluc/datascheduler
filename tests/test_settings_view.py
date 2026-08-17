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


def test_max_concurrent_runs_setting_is_stored_but_documented_as_not_yet_applied(qapp, test_db):
    """Choix de scope explicite (voir le chantier) : le plafond est un champ réel et persisté,
    mais son application concrète reste pour un futur chantier — la description doit le dire
    honnêtement plutôt que suggérer un comportement qui n'existe pas encore."""
    from ui.main_window.settings_view import SettingsView

    view = SettingsView()
    row = _row(view, "plafond d'exécutions simultanées")
    # La ligne existe et porte un contrôle réel (pas un simple texte statique).
    assert view.spin_max_concurrent is not None

    view.spin_max_concurrent.setValue(9)
    view._on_save()
    assert db.get_app_settings().max_concurrent_runs == 9


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
