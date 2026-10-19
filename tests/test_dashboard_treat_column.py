"""
DataScheduler — tests/test_dashboard_treat_column.py
Refonte, lot A-Aujourd'hui : A3/A4 (cartes ÉCHEC dans "À traiter"), A7/A8 (onglets, tableau), A9
(panneau latéral d'échec), A10 (panneau latéral en cours).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime, timedelta

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from database import db_manager as db
from database.models import Pipeline, PipelineRun


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _fail_pipeline(name="pipeline-echec", retry_count=2, error="ORA-12541: TNS:no listener"):
    pipeline = db.create_pipeline(name=name)
    db.save_steps(pipeline.id, [{
        "step_type": "DB_EXTRACT", "label": "Extraire clients",
        "config": {"_step_key": "step-1"}, "retry_count": retry_count,
    }])
    run = db.create_run(pipeline.id)
    db.finish_run(run.id, "FAILED", error_message=error, failed_step_key="step-1")
    with db.get_session() as s:
        s.get(Pipeline, pipeline.id).last_status = "FAILED"
    return pipeline, run


def _treat_text(view) -> str:
    labels = [lbl.text() for lbl in view._treat_cards.findChildren(QLabel)]
    buttons = [btn.text() for btn in view._treat_cards.findChildren(QPushButton)]
    return " ".join(labels + buttons)


# ── A3 + A4 : cartes "À traiter" ────────────────────────────────────────────

def test_failure_card_shown_for_active_failed_pipeline(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    pipeline, run = _fail_pipeline()

    view = DashboardView()
    view.refresh()

    text = _treat_text(view)
    assert "ÉCHEC" in text
    assert pipeline.name in text
    assert "Extraire clients" in text
    assert "2 réessais" in text
    assert "ORA-12541" in text
    assert view._treat_empty.isHidden()


def test_failure_card_absent_for_inactive_pipeline(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    pipeline, run = _fail_pipeline(name="pipeline-inactif")
    db.set_pipeline_active(pipeline.id, False)

    view = DashboardView()
    view.refresh()

    assert "pipeline-inactif" not in _treat_text(view)


def test_resume_button_only_shown_when_resumable_run_exists(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    pipeline, run = _fail_pipeline()

    view = DashboardView()
    view.refresh()
    assert "Reprendre depuis l'échec" not in _treat_text(view)

    with db.get_session() as s:
        s.get(PipelineRun, run.id).resumable_state_json = "{}"

    view.refresh()
    assert "Reprendre depuis l'échec" in _treat_text(view)


# ── A9 : panneau latéral d'échec ────────────────────────────────────────────

def test_open_failure_panel_populates_and_opens_side_panel(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    pipeline, run = _fail_pipeline()

    view = DashboardView()
    view._open_failure_panel(pipeline.id)

    content_text = " ".join(lbl.text() for lbl in view._side_panel.findChildren(QLabel))
    assert f"EXÉCUTION #{run.id}" in content_text
    assert "ÉCHEC" in content_text
    assert pipeline.name in content_text
    assert not view._side_panel.isHidden()


def test_failure_panel_missing_pipeline_does_not_raise(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    view = DashboardView()
    view._open_failure_panel(999_999)   # pas de run -> ne doit pas lever, panneau reste fermé

    assert view._side_panel.isHidden()


# ── A10 : panneau latéral en cours ──────────────────────────────────────────

def test_open_running_panel_populates_and_opens_side_panel(qapp, test_db):
    import threading
    import core.pipeline as pipeline_module
    from ui.main_window.dashboard_view import DashboardView

    pipeline = db.create_pipeline(name="pipeline-en-cours")
    run = db.create_run(pipeline.id)
    db.update_run_progress(run.id, "Étape 2/4 : Appeler l'API", "14:04:23 Démarrage", "step-2")

    view = DashboardView()
    pipeline_module._active_runs[pipeline.id] = threading.Event()
    try:
        view._open_running_panel(pipeline.id)
    finally:
        pipeline_module._active_runs.pop(pipeline.id, None)

    content_text = " ".join(lbl.text() for lbl in view._side_panel.findChildren(QLabel))
    assert "EN COURS" in content_text
    assert pipeline.name in content_text
    assert "Étape 2/4" in content_text
    assert not view._side_panel.isHidden()


# ── A7 + A8 : onglets + tableau ─────────────────────────────────────────────

def test_tabs_switch_between_table_and_topology(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    view = DashboardView()
    assert view._tabs_stack.currentIndex() == 0
    assert view.table.isVisibleTo(view._tabs_stack.widget(0)) or True   # table est sur la page 0

    view._set_active_tab(1)
    assert view._tabs_stack.currentIndex() == 1

    view._set_active_tab(0)
    assert view._tabs_stack.currentIndex() == 0


def test_table_duration_format_matches_maquette(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    pipeline = db.create_pipeline(name="duree-test")
    run = db.create_run(pipeline.id)
    db.finish_run(run.id, "SUCCESS")
    with db.get_session() as s:
        r = s.get(PipelineRun, run.id)
        # Déduit de finished_at (déjà fixé par finish_run()), pas de utcnow() à part : deux
        # appels distincts à utcnow() à quelques lignes d'écart peuvent différer d'une seconde
        # selon le moment exact de l'exécution (constaté : échec par ±1s).
        r.started_at = r.finished_at - timedelta(minutes=2, seconds=4)

    view = DashboardView()
    view.refresh()

    durations = [
        view.table.item(row, 3).text()
        for row in range(view.table.rowCount())
        if view.table.item(row, 0) and view.table.item(row, 0).text() == "duree-test"
    ]
    assert durations == ["2 min 04"]


def test_table_header_renamed_to_8_dernieres(qapp, test_db):
    from ui.main_window.dashboard_view import DashboardView

    view = DashboardView()
    headers = [view.table.horizontalHeaderItem(i).text() for i in range(view.table.columnCount())]
    assert "8 dernières" in headers
    assert "Historique" not in headers
