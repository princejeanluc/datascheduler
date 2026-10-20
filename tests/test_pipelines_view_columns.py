"""
DataScheduler — tests/test_pipelines_view_columns.py
Refonte, lot A-Pipelines : A2 (colonne PIPELINE, description), A3 (colonne ÉTAT, ligne de
détail par état), A4 (colonne FORME · 8 DERNIERS, RunHistoryDots), A5 (colonne PLANIFICATION,
relation de déclenchement visible), A6 (colonne PROCHAINE, format relatif).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime, timedelta

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from database import db_manager as db
from database.models import Pipeline, PipelineRun


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _row_text(view, row: int) -> str:
    labels = []
    for col in (0, 1, 2):
        w = view.table.cellWidget(row, col)
        if w is not None:
            labels += [lbl.text() for lbl in w.findChildren(QLabel)]
    return " ".join(labels)


# ── A2 : nom + description ──────────────────────────────────────────────────

def test_name_column_shows_description_below_name(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    db.create_pipeline(name="Synchro clients CRM", description="Oracle CRM -> référentiel clients")

    view = PipelinesView()
    view.refresh()

    text = _row_text(view, 0)
    assert "Synchro clients CRM" in text
    assert "Oracle CRM -> référentiel clients" in text


def test_name_column_without_description_shows_only_name(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    db.create_pipeline(name="sans-description")

    view = PipelinesView()
    view.refresh()

    assert "sans-description" in _row_text(view, 0)


# ── A3 : ligne de détail par état ───────────────────────────────────────────

def test_state_detail_shows_time_and_error_on_failure(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="echec-test")
    db.save_steps(p.id, [{"step_type": "DB_EXTRACT"}])
    run = db.create_run(p.id)
    db.finish_run(run.id, "FAILED", error_message="ORA-12541: TNS:no listener")
    with db.get_session() as s:
        s.get(Pipeline, p.id).last_status = "FAILED"

    view = PipelinesView()
    view.refresh()

    assert "ORA-12541" in _row_text(view, 0)


def test_state_detail_shows_time_and_duration_on_success(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="succes-test")
    run = db.create_run(p.id)
    with db.get_session() as s:
        s.get(PipelineRun, run.id).started_at = datetime.utcnow() - timedelta(minutes=2, seconds=4)
    db.finish_run(run.id, "SUCCESS")
    with db.get_session() as s:
        s.get(Pipeline, p.id).last_status = "SUCCESS"

    view = PipelinesView()
    view.refresh()

    assert "2 min 04" in _row_text(view, 0)


def test_state_detail_shows_step_and_elapsed_while_running(qapp, test_db):
    import threading
    import core.pipeline as pipeline_module
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="encours-test")
    run = db.create_run(p.id)
    db.update_run_progress(run.id, "Étape 2/4 : Appeler l'API", "log", "step-2")
    with db.get_session() as s:
        s.get(Pipeline, p.id).last_status = "RUNNING"

    pipeline_module._active_runs[p.id] = threading.Event()
    try:
        view = PipelinesView()
        view.refresh()
        text = _row_text(view, 0)
    finally:
        pipeline_module._active_runs.pop(p.id, None)

    assert "étape 2/4" in text


def test_state_detail_shows_expected_time_when_missed(qapp, test_db):
    from core import missed_runs
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="manque-test")
    missed_runs._pending[p.id] = {
        "pipeline_id": p.id, "name": p.name,
        "expected_at": datetime(2026, 10, 19, 3, 0), "late_minutes": 180,
    }

    view = PipelinesView()
    view.refresh()

    text = _row_text(view, 0)
    assert "MANQUÉ" in text
    assert "prévue 03:00" in text


def test_state_detail_shows_inactif_for_inactive_pipeline(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="inactif-test")
    db.set_pipeline_active(p.id, False)

    view = PipelinesView()
    view.refresh()

    assert _row_text(view, 0).count("Inactif") >= 1


def test_missed_takes_priority_over_running_badge_only_when_not_running(qapp, test_db):
    """Un pipeline en cours ne doit jamais afficher MANQUÉ même s'il a par ailleurs une entrée
    en attente (cas extrême, priorité documentée dans _pipeline_state_detail)."""
    import threading
    import core.pipeline as pipeline_module
    from core import missed_runs
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="encours-et-manque")
    run = db.create_run(p.id)
    db.update_run_progress(run.id, "Étape 1/1 : X", "log", "step-1")
    with db.get_session() as s:
        s.get(Pipeline, p.id).last_status = "RUNNING"
    missed_runs._pending[p.id] = {
        "pipeline_id": p.id, "name": p.name,
        "expected_at": datetime.utcnow(), "late_minutes": 10,
    }
    pipeline_module._active_runs[p.id] = threading.Event()
    try:
        view = PipelinesView()
        view.refresh()
        text = _row_text(view, 0)
    finally:
        pipeline_module._active_runs.pop(p.id, None)

    assert "MANQUÉ" not in text
    assert "RUNNING" in text


# ── A4 : pastilles des 8 derniers runs ──────────────────────────────────────

def test_steps_column_includes_run_history_dots(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView
    from ui.main_window.widgets import RunHistoryDots

    p = db.create_pipeline(name="dots-test")
    for _ in range(3):
        run = db.create_run(p.id)
        db.finish_run(run.id, "SUCCESS")

    view = PipelinesView()
    view.refresh()

    cell = view.table.cellWidget(0, 2)
    assert cell.findChild(RunHistoryDots) is not None


# ── A5 : relation de déclenchement visible ──────────────────────────────────

def test_planning_column_shows_relation_line_when_triggered(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    parent = db.create_pipeline(name="parent-test")
    child = db.create_pipeline(name="child-test")
    db.save_steps(child.id, [{"step_type": "DB_EXTRACT"}])
    db.set_pipeline_trigger(child.id, parent.id, "SUCCESS")

    view = PipelinesView()
    view.refresh()

    row = next(
        r for r in range(view.table.rowCount())
        if "child-test" in view.table.cellWidget(r, 0).findChildren(QLabel)[0].text()
    )
    cell = view.table.cellWidget(row, 3)
    assert cell is not None
    text = " ".join(lbl.text() for lbl in cell.findChildren(QLabel))
    assert "après parent-test" in text
    assert "si réussite" in text


def test_planning_column_stays_plain_item_without_trigger(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    db.create_pipeline(name="no-trigger-test")

    view = PipelinesView()
    view.refresh()

    assert view.table.cellWidget(0, 3) is None
    assert view.table.item(0, 3) is not None


# ── A6 : colonne PROCHAINE au format relatif ────────────────────────────────

def test_next_run_same_day_shows_bare_time(qapp, test_db):
    from ui.main_window.pipelines_view import _format_next_run
    from ui.time_display import to_display

    today = to_display(datetime.utcnow()).date()
    next_run = datetime(today.year, today.month, today.day, 16, 0)
    assert _format_next_run(next_run) == "16:00"


def test_next_run_tomorrow_shows_demain_prefix(qapp, test_db):
    from ui.main_window.pipelines_view import _format_next_run
    from ui.time_display import to_display

    tomorrow = to_display(datetime.utcnow()).date() + timedelta(days=1)
    next_run = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 7, 0)
    assert _format_next_run(next_run) == "demain 07:00"


def test_next_run_further_out_shows_date(qapp, test_db):
    from ui.main_window.pipelines_view import _format_next_run

    far = datetime.utcnow() + timedelta(days=10)
    result = _format_next_run(datetime(far.year, far.month, far.day, 5, 0))
    assert result == far.strftime("%d/%m 05:00")


def test_next_run_none_shows_dash(qapp, test_db):
    from ui.main_window.pipelines_view import _format_next_run

    assert _format_next_run(None) == "—"
