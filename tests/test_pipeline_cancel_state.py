"""
DataScheduler — tests/test_pipeline_cancel_state.py
Vérifie is_cancel_requested() (core/pipeline.py) et son affichage dans PipelinesView : une
interruption demandée mais pas encore effective doit rester visible ("Arrêt en cours") plutôt que
de laisser l'utilisateur sans retour tant que l'étape en cours ne s'est pas terminée (persona
"Karim", étude UX).
"""

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from core import pipeline as pipeline_module
from core.pipeline import is_pipeline_running, is_cancel_requested, request_cancel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _clean_active_runs():
    pipeline_module._active_runs.clear()
    yield
    pipeline_module._active_runs.clear()


def test_is_cancel_requested_false_when_not_running():
    assert not is_pipeline_running(123)
    assert not is_cancel_requested(123)


def test_is_cancel_requested_false_before_request_cancel():
    pipeline_module._active_runs[123] = threading.Event()
    assert is_pipeline_running(123)
    assert not is_cancel_requested(123)


def test_is_cancel_requested_true_after_request_cancel():
    pipeline_module._active_runs[123] = threading.Event()
    assert request_cancel(123)
    assert is_cancel_requested(123)


def test_request_cancel_returns_false_when_nothing_running():
    assert not request_cancel(999)


def test_pipelines_view_shows_stopping_badge_while_cancel_pending(qapp, test_db):
    from database import db_manager as db
    from ui.main_window.pipelines_view import PipelinesView

    pipeline = db.create_pipeline(name="cancel-badge-test")
    db.save_steps(pipeline.id, [{"step_type": "DB_EXTRACT", "config": {}}])
    with db.get_session() as s:
        from database.models import Pipeline
        p = s.get(Pipeline, pipeline.id)
        p.last_status = "RUNNING"

    pipeline_module._active_runs[pipeline.id] = threading.Event()
    request_cancel(pipeline.id)

    view = PipelinesView()
    badge = view.table.cellWidget(0, 1)
    assert badge.text() == "ARRÊT EN COURS"


def test_pipelines_view_shows_running_badge_without_cancel_pending(qapp, test_db):
    from database import db_manager as db
    from ui.main_window.pipelines_view import PipelinesView

    pipeline = db.create_pipeline(name="running-no-cancel-test")
    db.save_steps(pipeline.id, [{"step_type": "DB_EXTRACT", "config": {}}])
    with db.get_session() as s:
        from database.models import Pipeline
        p = s.get(Pipeline, pipeline.id)
        p.last_status = "RUNNING"

    pipeline_module._active_runs[pipeline.id] = threading.Event()   # actif, pas d'arrêt demandé

    view = PipelinesView()
    badge = view.table.cellWidget(0, 1)
    assert badge.text() == "RUNNING"


def test_pipelines_view_running_badge_shows_current_step_as_tooltip(qapp, test_db):
    """chantier N — l'infobulle du badge RUNNING reflète PipelineRun.current_step_label,
    persisté en continu par run_pipeline(), pas seulement à la fin."""
    from database import db_manager as db
    from ui.main_window.pipelines_view import PipelinesView

    pipeline = db.create_pipeline(name="running-tooltip-test")
    db.save_steps(pipeline.id, [{"step_type": "DB_EXTRACT", "config": {}}])
    with db.get_session() as s:
        from database.models import Pipeline
        p = s.get(Pipeline, pipeline.id)
        p.last_status = "RUNNING"

    run = db.create_run(pipeline.id)
    db.update_run_progress(run.id, "Étape 1/3 : Extraction", "…")

    pipeline_module._active_runs[pipeline.id] = threading.Event()

    view = PipelinesView()
    badge = view.table.cellWidget(0, 1)
    assert badge.toolTip() == "Étape 1/3 : Extraction"


def test_pipelines_view_non_running_badge_has_no_step_tooltip(qapp, test_db):
    from database import db_manager as db
    from ui.main_window.pipelines_view import PipelinesView

    pipeline = db.create_pipeline(name="idle-tooltip-test")
    db.save_steps(pipeline.id, [{"step_type": "DB_EXTRACT", "config": {}}])

    view = PipelinesView()
    badge = view.table.cellWidget(0, 1)
    assert badge.toolTip() == ""
