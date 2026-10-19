"""
DataScheduler — tests/test_dashboard_header.py
Refonte, lot A-Aujourd'hui, A1 : en-tête via make_page_header (surtitre date/heure en français,
titre statique "Aujourd'hui", nouveau signal new_pipeline_requested).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_today_eyebrow_formats_french_day_and_month_uppercase(qapp, test_db):
    from ui.main_window.dashboard_view import _today_eyebrow, _DAYS_FR, _MONTHS_FR

    text = _today_eyebrow()
    # Pas d'assertion sur la date exacte (dépend du jour d'exécution) — juste la forme :
    # "JOUR N MOIS · HH:MM", jour/mois tirés des listes françaises, en majuscules.
    assert "·" in text
    assert any(d.upper() in text for d in _DAYS_FR)
    assert any(m.upper() in text for m in _MONTHS_FR)


def test_dashboard_header_shows_static_aujourdhui_title(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView
    from PySide6.QtWidgets import QLabel

    view = DashboardView()
    title_lbl = view.findChild(QLabel, "page_title")
    assert title_lbl is not None
    assert title_lbl.text() == "Aujourd'hui"


def test_dashboard_refresh_updates_the_eyebrow_label(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    view = DashboardView()
    view._eyebrow_lbl.setText("texte perime")

    view.refresh()

    assert view._eyebrow_lbl.text() != "texte perime"


def test_new_pipeline_button_emits_new_pipeline_requested(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    view = DashboardView()
    received = []
    view.new_pipeline_requested.connect(lambda: received.append(True))

    view._btn_new_pipeline.click()

    assert received == [True]
