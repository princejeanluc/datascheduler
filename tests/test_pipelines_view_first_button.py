"""
DataScheduler — tests/test_pipelines_view_first_button.py
Refonte, lot A-Pipelines : A7 (DECISIONS.md::P8) — le premier bouton de chaque ligne change selon
l'état du pipeline : reprendre si reprenable, arrêter si en cours, lancer sinon.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from database import db_manager as db
from database.models import PipelineRun


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _first_button(view, row: int) -> QPushButton:
    return view.table.cellWidget(row, 5).findChildren(QPushButton)[0]


def test_first_button_launches_by_default(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="default-run-test")
    view = PipelinesView()

    btn = _first_button(view, 0)
    assert btn.toolTip() == "Exécuter maintenant"
    assert btn.objectName() == "accent_action"

    calls = []
    monkeypatch.setattr(view, "_on_run_pipeline", lambda i: calls.append(i))
    btn.click()
    assert calls == [p.id]


def test_first_button_stops_while_running(qapp, test_db, monkeypatch):
    import core.pipeline as pipeline_module
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="running-stop-test")
    monkeypatch.setattr(pipeline_module, "is_pipeline_running", lambda pid: True)
    view = PipelinesView()

    btn = _first_button(view, 0)
    assert btn.toolTip() == "Interrompre"
    assert btn.objectName() == "secondary"

    calls = []
    monkeypatch.setattr(view, "_on_interrupt_pipeline", lambda i, n: calls.append((i, n)))
    btn.click()
    assert calls == [(p.id, "running-stop-test")]


def test_first_button_resumes_when_resumable(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="resumable-test")
    run = db.create_run(p.id)
    with db.get_session() as s:
        s.get(PipelineRun, run.id).resumable_state_json = "{}"

    view = PipelinesView()
    btn = _first_button(view, 0)
    assert btn.toolTip() == "Reprendre depuis l'échec"
    assert btn.objectName() == "accent_action"

    calls = []
    monkeypatch.setattr(view, "_on_resume_pipeline", lambda i, n, r: calls.append((i, n, r)))
    btn.click()
    assert calls == [(p.id, "resumable-test", run.id)]


def test_first_button_stays_secondary_style_when_inactive(qapp, test_db, monkeypatch):
    """Même quand un run reprenable existe, un pipeline inactif garde le bouton neutre — jamais
    mis en avant visuellement (maquette : ligne grisée, boutons restent outline)."""
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="inactive-resumable-test")
    run = db.create_run(p.id)
    with db.get_session() as s:
        s.get(PipelineRun, run.id).resumable_state_json = "{}"
    db.set_pipeline_active(p.id, False)

    view = PipelinesView()
    btn = _first_button(view, 0)
    assert btn.toolTip() == "Exécuter maintenant"
    assert btn.objectName() == "secondary"
