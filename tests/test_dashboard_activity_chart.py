"""
DataScheduler — tests/test_dashboard_activity_chart.py
Fumée (offscreen Qt) : le Dashboard alimente bien son ActivityChartWidget via
db.get_run_counts_by_day() lors du refresh() (chantier UX statistiques/graphiques, B.3).
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


def test_dashboard_populates_activity_chart_on_load(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    pipeline = db.create_pipeline(name="dashboard-chart-test")
    run = db.create_run(pipeline.id)
    db.finish_run(run.id, status="SUCCESS", rows_exported=5)

    view = DashboardView()
    assert len(view.chart._data) == 30
    assert view.chart._data[-1]["success"] == 1


def test_dashboard_refresh_updates_chart(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    pipeline = db.create_pipeline(name="dashboard-chart-refresh")
    view = DashboardView()
    assert view.chart._data[-1]["failed"] == 0

    run = db.create_run(pipeline.id)
    db.finish_run(run.id, status="FAILED", error_message="boom")
    view.refresh()
    assert view.chart._data[-1]["failed"] == 1
