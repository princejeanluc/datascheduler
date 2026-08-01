"""
DataScheduler — tests/test_activity_chart.py
Fumée (offscreen Qt) : ActivityChartWidget (chantier UX statistiques/graphiques, B.2) stocke bien
les données de set_data(), et le rendu réel (paintEvent, forcé via grab()) ne lève pas
d'exception sur un jeu de données varié (vide, un seul jour, 30 jours, jour à un seul statut).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date, timedelta

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from ui.main_window.activity_chart import ActivityChartWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_days(n: int, **overrides) -> list[dict]:
    today = date.today()
    days = []
    for i in range(n):
        d = today - timedelta(days=n - 1 - i)
        entry = {"date": d, "success": 0, "failed": 0, "cancelled": 0}
        entry.update(overrides)
        days.append(entry)
    return days


def test_set_data_stores_and_computes_max(qapp):
    w = ActivityChartWidget()
    data = [
        {"date": date.today(), "success": 3, "failed": 1, "cancelled": 0},
        {"date": date.today() - timedelta(days=1), "success": 5, "failed": 0, "cancelled": 2},
    ]
    w.set_data(data)
    assert w._data == data
    assert w._max_total == 7  # 5 + 0 + 2, le plus grand total journalier


def test_max_total_defaults_to_one_when_all_zero(qapp):
    w = ActivityChartWidget()
    w.set_data(_make_days(5))
    assert w._max_total == 1


def test_paint_does_not_raise_on_empty_data(qapp):
    w = ActivityChartWidget()
    w.resize(400, 150)
    w.set_data([])
    w.grab()  # force un rendu réel


def test_paint_does_not_raise_on_single_day(qapp):
    w = ActivityChartWidget()
    w.resize(400, 150)
    w.set_data([{"date": date.today(), "success": 2, "failed": 1, "cancelled": 0}])
    w.grab()


def test_paint_does_not_raise_on_thirty_days_varied(qapp):
    w = ActivityChartWidget()
    w.resize(400, 150)
    data = []
    today = date.today()
    for i in range(30):
        data.append({
            "date": today - timedelta(days=29 - i),
            "success": i % 4, "failed": i % 3, "cancelled": 1 if i % 5 == 0 else 0,
        })
    w.set_data(data)
    w.grab()


def test_bar_index_at_returns_none_outside_plot(qapp):
    w = ActivityChartWidget()
    w.resize(400, 150)
    w.set_data(_make_days(10))
    assert w._bar_index_at(QPointF(-5, 60)) is None
    assert w._bar_index_at(QPointF(10, 5)) is None


def test_bar_index_at_maps_left_to_right_chronologically(qapp):
    w = ActivityChartWidget()
    w.resize(400, 150)
    w.set_data(_make_days(10))
    plot = w._plot_rect()
    idx_left = w._bar_index_at(QPointF(plot.left() + 1, plot.center().y()))
    idx_right = w._bar_index_at(QPointF(plot.right() - 1, plot.center().y()))
    assert idx_left == 0
    assert idx_right == 9
