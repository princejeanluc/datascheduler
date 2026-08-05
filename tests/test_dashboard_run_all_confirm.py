"""
DataScheduler — tests/test_dashboard_run_all_confirm.py
Fumée (offscreen Qt) : "Tout exécuter" (Dashboard, chantier UX ergonomie E.1) ne déclenche plus
aucun pipeline sans confirmation — action la plus destructrice de l'app, désormais un clic ne
suffit plus. QMessageBox.question mocké pour simuler Oui/Non sans bloquer sur .exec().
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeScheduler:
    def __init__(self):
        self.triggered = []

    def trigger_now(self, pipeline_id):
        self.triggered.append(pipeline_id)


def test_run_all_does_nothing_when_user_declines(qapp, test_db, monkeypatch):
    from ui.main_window import dashboard_view as dv_module

    p = db.create_pipeline(name="run-all-decline-test")

    fake_sched = _FakeScheduler()
    monkeypatch.setattr("core.scheduler.get_scheduler", lambda: fake_sched)
    monkeypatch.setattr(dv_module.QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))
    monkeypatch.setattr(dv_module.QMessageBox, "information", staticmethod(lambda *a, **k: None))

    view = dv_module.DashboardView()
    view._on_run_all()

    assert fake_sched.triggered == []


def test_run_all_triggers_pipelines_when_user_confirms(qapp, test_db, monkeypatch):
    from ui.main_window import dashboard_view as dv_module

    p = db.create_pipeline(name="run-all-confirm-test")

    fake_sched = _FakeScheduler()
    monkeypatch.setattr("core.scheduler.get_scheduler", lambda: fake_sched)
    monkeypatch.setattr(dv_module.QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(dv_module.QMessageBox, "information", staticmethod(lambda *a, **k: None))

    view = dv_module.DashboardView()
    view._on_run_all()

    assert fake_sched.triggered == [p.id]
