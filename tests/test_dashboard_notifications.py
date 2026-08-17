"""
DataScheduler — tests/test_dashboard_notifications.py
Fumée (offscreen Qt) : la ligne d'un run en échec ressort visuellement dans le Dashboard
(persona "Karim" — repérer un échec en un coup d'œil) et la catégorie "Notifications" de
SettingsView enregistre correctement le digest (persona "Sophie") — migré depuis l'ancien
NotificationSettingsDialog, retiré au profit de l'écran Paramètres unifié.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from database import db_manager as db
from ui.styles import COLORS


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_failed_run_pipeline_name_is_highlighted(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    pipeline = db.create_pipeline(name="dashboard-failed-test")
    run = db.create_run(pipeline.id)
    db.finish_run(run.id, status="FAILED", error_message="Table introuvable")

    view = DashboardView()
    item = view.table.item(0, 0)
    assert item.text() == "dashboard-failed-test"
    assert item.foreground().color() == QColor(COLORS["danger"])
    assert item.font().bold()
    assert item.toolTip() == "Table introuvable"


def test_successful_run_is_not_highlighted(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    pipeline = db.create_pipeline(name="dashboard-success-test")
    run = db.create_run(pipeline.id)
    db.finish_run(run.id, status="SUCCESS", rows_exported=10)

    view = DashboardView()
    item = view.table.item(0, 0)
    assert item.foreground().color() == QColor(COLORS["text_main"])
    assert not item.font().bold()
    assert item.toolTip() == ""


def _row_wrapper(view, label_substr: str):
    """Retrouve le wrapper d'une ligne de SettingsView par une sous-chaîne (insensible à la
    casse) de son libellé — évite de dépendre de l'ordre d'ajout des lignes."""
    return next(r["wrapper"] for r in view._row_widgets if label_substr in r["label"])


def test_settings_view_saves_notification_fields(qapp, test_db):
    """Migration du digest email vers l'écran Paramètres unifié (retrait de
    NotificationSettingsDialog) — même vérification qu'avant : les champs se sauvegardent et le
    job de digest est bien (re)planifié auprès d'APScheduler."""
    from core.scheduler import init_scheduler
    from ui.main_window.settings_view import SettingsView

    sched = init_scheduler()
    try:
        smtp = db.create_smtp_profile(name="SMTP_TEST", host="h", port=587, from_address="a@b.c")

        view = SettingsView()
        assert not view.chk_digest_enabled.isChecked()

        view.chk_digest_enabled.setChecked(True)
        idx = view.cb_smtp.findData(smtp.id)
        view.cb_smtp.setCurrentIndex(idx)
        view.inp_recipients.setText("dest@test.com")
        view._on_save()

        settings = db.get_notification_settings()
        assert settings.digest_enabled
        assert settings.digest_smtp_profile_id == smtp.id
        assert settings.digest_recipients == "dest@test.com"
        assert sched._scheduler.get_job(sched.DIGEST_JOB_ID) is not None
    finally:
        sched.stop()
        import core.scheduler as scheduler_module
        scheduler_module._scheduler_instance = None


def test_settings_view_day_row_only_visible_for_weekly_notifications_category(qapp, test_db):
    from ui.main_window.settings_view import SettingsView

    view = SettingsView()
    view.select_category("notifications")
    day_row = _row_wrapper(view, "jour (si")
    assert day_row.isHidden()   # DAILY par défaut

    view.cb_frequency.setCurrentIndex(view.cb_frequency.findData("WEEKLY"))
    assert not day_row.isHidden()

    view.cb_frequency.setCurrentIndex(view.cb_frequency.findData("DAILY"))
    assert day_row.isHidden()


def test_settings_view_saves_time_and_day(qapp, test_db):
    from core.scheduler import init_scheduler
    from ui.main_window.settings_view import SettingsView

    sched = init_scheduler()
    try:
        smtp = db.create_smtp_profile(name="SMTP_TEST2", host="h", port=587, from_address="a@b.c")

        view = SettingsView()
        view.chk_digest_enabled.setChecked(True)
        view.cb_smtp.setCurrentIndex(view.cb_smtp.findData(smtp.id))
        view.inp_recipients.setText("dest@test.com")
        view.cb_frequency.setCurrentIndex(view.cb_frequency.findData("WEEKLY"))
        view.inp_time.setText("22:30")
        view.cb_day.setCurrentIndex(view.cb_day.findData(5))
        view._on_save()

        settings = db.get_notification_settings()
        assert settings.digest_time == "22:30"
        assert settings.digest_day_of_week == 5
    finally:
        sched.stop()
        import core.scheduler as scheduler_module
        scheduler_module._scheduler_instance = None


def test_settings_view_prefill_restores_time_and_day(qapp, test_db):
    from ui.main_window.settings_view import SettingsView

    db.update_notification_settings(digest_time="14:20", digest_day_of_week=2, digest_frequency="WEEKLY")
    view = SettingsView()
    assert view.inp_time.text() == "14:20"
    assert view.cb_day.currentData() == 2

    view.select_category("notifications")
    assert not _row_wrapper(view, "jour (si").isHidden()


def test_settings_view_rejects_invalid_time(qapp, test_db, monkeypatch):
    from ui.main_window import settings_view as sv_module
    from ui.main_window.settings_view import SettingsView

    warnings = []
    monkeypatch.setattr(
        sv_module.QMessageBox, "warning",
        lambda *a, **kw: warnings.append(a) or None,
    )

    view = SettingsView()
    view.chk_digest_enabled.setChecked(False)
    view.inp_time.setText("99:99")
    view._on_save()

    assert warnings   # QMessageBox.warning appelé, pas d'enregistrement silencieux d'une heure invalide
