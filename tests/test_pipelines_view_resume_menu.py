"""
DataScheduler — tests/test_pipelines_view_resume_menu.py
Fumée (offscreen Qt) : l'action "Reprendre depuis l'échec" du menu "⋯" de PipelinesView
(chantier J.2) n'apparaît que si un état de reprise existe pour ce pipeline, et déclenche le bon
callback avec le bon run_id. Même patron que test_pipelines_view_action_menu.py.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _get_more_button_and_menu(view, row: int):
    cell = view.table.cellWidget(row, 5)
    for btn in cell.findChildren(QPushButton):
        menu = btn.menu()
        if menu is not None:
            return btn, menu
    raise AssertionError("Aucun bouton avec menu trouvé dans la cellule Actions.")


def test_resume_action_absent_without_resumable_state(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    db.create_pipeline(name="no-resume-test")
    view = PipelinesView()
    _, menu = _get_more_button_and_menu(view, 0)
    labels = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert "Reprendre depuis l'échec" not in labels


def test_resume_action_present_and_wired_when_resumable_state_exists(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    p = db.create_pipeline(name="resume-test")
    run = db.create_run(p.id)
    db.finish_run(run.id, status="FAILED", error_message="échec simulé",
                  resumable_state_json='{"completed_step_keys": ["a"], "artifacts": {}}')

    view = PipelinesView()
    _, menu = _get_more_button_and_menu(view, 0)
    labels = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert "Reprendre depuis l'échec" in labels

    calls = []
    monkeypatch.setattr(view, "_on_resume_pipeline", lambda i, n, r: calls.append((i, n, r)))
    resume_action = next(a for a in menu.actions() if a.text() == "Reprendre depuis l'échec")
    resume_action.trigger()

    assert calls == [(p.id, "resume-test", run.id)]
