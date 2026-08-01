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
