"""
DataScheduler — tests/test_dashboard_active_pipelines_count.py
Correctif K6 (docs/refonte/LOTS.md) : la carte "Pipelines actifs" du Dashboard comptait tous les
pipelines (len(pipelines)), actifs et inactifs confondus, malgré son libellé.
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


def test_active_pipelines_card_excludes_inactive_pipelines(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    db.create_pipeline(name="actif-1")
    db.create_pipeline(name="actif-2")
    p3 = db.create_pipeline(name="inactif-1")
    db.set_pipeline_active(p3.id, False)

    view = DashboardView()
    view.refresh()

    assert view._card_active._lbl_value.text() == "2"
