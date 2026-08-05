"""
DataScheduler — tests/test_dashboard_notifications.py
Fumée (offscreen Qt) : la ligne d'un run en échec ressort visuellement dans le Dashboard
(persona "Karim" — repérer un échec en un coup d'œil) et NotificationSettingsDialog s'ouvre et
enregistre correctement (persona "Sophie").
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


def test_notification_settings_dialog_opens_and_saves(qapp, test_db):
    from core.scheduler import init_scheduler
    from ui.dialogs import NotificationSettingsDialog

    sched = init_scheduler()
    try:
        smtp = db.create_smtp_profile(name="SMTP_TEST", host="h", port=587, from_address="a@b.c")

        dlg = NotificationSettingsDialog(None)
        assert dlg.windowTitle()
        assert not dlg.chk_enabled.isChecked()

        dlg.chk_enabled.setChecked(True)
        idx = dlg.cb_smtp.findData(smtp.id)
        dlg.cb_smtp.setCurrentIndex(idx)
        dlg.inp_recipients.setText("dest@test.com")
        dlg._on_save()

        settings = db.get_notification_settings()
        assert settings.digest_enabled
        assert settings.digest_smtp_profile_id == smtp.id
        assert settings.digest_recipients == "dest@test.com"
        assert sched._scheduler.get_job(sched.DIGEST_JOB_ID) is not None
    finally:
        sched.stop()
        import core.scheduler as scheduler_module
        scheduler_module._scheduler_instance = None


def test_notification_settings_dialog_day_combo_only_visible_for_weekly(qapp, test_db):
    from ui.dialogs import NotificationSettingsDialog

    dlg = NotificationSettingsDialog(None)
    assert dlg.cb_day.isHidden()   # DAILY par défaut

    dlg.cb_frequency.setCurrentIndex(dlg.cb_frequency.findData("WEEKLY"))
    assert not dlg.cb_day.isHidden()

    dlg.cb_frequency.setCurrentIndex(dlg.cb_frequency.findData("DAILY"))
    assert dlg.cb_day.isHidden()


def test_notification_settings_dialog_saves_time_and_day(qapp, test_db):
    from core.scheduler import init_scheduler
    from ui.dialogs import NotificationSettingsDialog

    sched = init_scheduler()
    try:
        smtp = db.create_smtp_profile(name="SMTP_TEST2", host="h", port=587, from_address="a@b.c")

        dlg = NotificationSettingsDialog(None)
        dlg.chk_enabled.setChecked(True)
        dlg.cb_smtp.setCurrentIndex(dlg.cb_smtp.findData(smtp.id))
        dlg.inp_recipients.setText("dest@test.com")
        dlg.cb_frequency.setCurrentIndex(dlg.cb_frequency.findData("WEEKLY"))
        dlg.inp_time.setText("22:30")
        dlg.cb_day.setCurrentIndex(dlg.cb_day.findData(5))
        dlg._on_save()

        settings = db.get_notification_settings()
        assert settings.digest_time == "22:30"
        assert settings.digest_day_of_week == 5
    finally:
        sched.stop()
        import core.scheduler as scheduler_module
        scheduler_module._scheduler_instance = None


def test_notification_settings_dialog_prefill_restores_time_and_day(qapp, test_db):
    from ui.dialogs import NotificationSettingsDialog

    db.update_notification_settings(digest_time="14:20", digest_day_of_week=2, digest_frequency="WEEKLY")
    dlg = NotificationSettingsDialog(None)
    assert dlg.inp_time.text() == "14:20"
    assert dlg.cb_day.currentData() == 2
    assert not dlg.cb_day.isHidden()


def test_notification_settings_dialog_rejects_invalid_time(qapp, test_db, monkeypatch):
    from ui.dialogs import notification_settings_dialog as nsd_module
    from ui.dialogs import NotificationSettingsDialog

    warnings = []
    monkeypatch.setattr(
        nsd_module.QMessageBox, "warning",
        lambda *a, **kw: warnings.append(a) or None,
    )

    dlg = NotificationSettingsDialog(None)
    dlg.chk_enabled.setChecked(False)
    dlg.inp_time.setText("99:99")
    dlg._on_save()

    assert warnings   # QMessageBox.warning appelé, pas d'enregistrement silencieux d'une heure invalide
