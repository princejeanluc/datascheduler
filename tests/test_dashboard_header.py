"""
DataScheduler — tests/test_dashboard_header.py
Refonte, lot A-Aujourd'hui : A1 (en-tête via make_page_header, surtitre date/heure en français,
titre statique "Aujourd'hui", nouveau signal new_pipeline_requested) et A2 (rail en 2 groupes
MAINTENANT / ENSUITE).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime

import pytest
from PySide6.QtWidgets import QApplication

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _rail_text(view) -> str:
    """Texte concaténé de tous les QLabel du rail — les puces (_make_rail_chip) sont des QFrame
    avec des QLabel imbriqués, pas des enfants directs du layout eux-mêmes porteurs de texte."""
    from PySide6.QtWidgets import QLabel
    return " ".join(lbl.text() for lbl in view._rail.findChildren(QLabel))


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


# ── A2 : rail en 2 groupes MAINTENANT / ENSUITE ─────────────────────────────

def test_rail_shows_maintenant_group_with_step_label_for_a_running_pipeline(qapp, test_db):
    import threading
    import core.pipeline as pipeline_module
    from ui.main_window.dashboard_view import DashboardView

    pipeline = db.create_pipeline(name="rail-running-test")
    run = db.create_run(pipeline.id)   # started_at ~ maintenant, en cours
    db.update_run_progress(run.id, "Étape 2/4 : Appeler l'API", "", "step-2")

    pipeline_module._active_runs[pipeline.id] = threading.Event()
    try:
        view = DashboardView()
        view.refresh()
    finally:
        pipeline_module._active_runs.pop(pipeline.id, None)

    texts = _rail_text(view)
    assert "MAINTENANT" in texts
    assert "rail-running-test" in texts
    assert "Étape 2/4" in texts


def test_rail_shows_ensuite_group_for_upcoming_pipelines(qapp, test_db):
    from datetime import datetime, timedelta
    from database.models import Pipeline
    from ui.main_window.dashboard_view import DashboardView

    pipeline = db.create_pipeline(name="rail-upcoming-test")
    with db.get_session() as s:
        s.get(Pipeline, pipeline.id).next_run_at = datetime.utcnow() + timedelta(hours=2)

    view = DashboardView()
    view.refresh()

    texts = _rail_text(view)
    assert "ENSUITE" in texts
    assert "MAINTENANT" not in texts
    assert "rail-upcoming-test" in texts
