"""
DataScheduler — tests/test_history_view_graph_link.py
Chantier UX éditeur, Lot 1 (B1b) : bouton "Voir dans le graphe" sur une ligne d'historique en
échec — ouvre PipelineGraphEditorDialog avec le nœud fautif surligné. Visible seulement quand
run.status == "FAILED" ET run.failed_step_key est renseigné (pas status seul — certains échecs
n'ont jamais traversé la boucle d'étapes, voir core/pipeline.py, et n'ont donc jamais de
failed_step_key, y compris toute ligne antérieure à la migration de cette colonne).
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


def _buttons_in_row(view, row):
    widget = view.table.cellWidget(row, 6)
    return widget.findChildren(QPushButton)


def _has_graph_link_button(view, row):
    return any(
        b.toolTip() == "Voir dans le graphe" for b in _buttons_in_row(view, row)
    )


def test_graph_link_hidden_for_a_successful_run(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    pipeline = db.create_pipeline(name="hist-graph-link-success")
    run = db.create_run(pipeline.id)
    db.finish_run(run.id, status="SUCCESS")

    view = HistoryView()

    assert not _has_graph_link_button(view, 0)


def test_graph_link_hidden_for_a_failed_run_without_step_key(qapp, test_db):
    """Échec survenu hors de la boucle d'étapes (pipeline introuvable, plafond de concurrence,
    exception générique) — pas de nœud à montrer, le bouton ne doit pas apparaître."""
    from ui.main_window.history_view import HistoryView

    pipeline = db.create_pipeline(name="hist-graph-link-no-key")
    run = db.create_run(pipeline.id)
    db.finish_run(run.id, status="FAILED", error_message="échec générique")

    view = HistoryView()

    assert not _has_graph_link_button(view, 0)


def test_graph_link_visible_for_a_failed_run_with_step_key(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    pipeline = db.create_pipeline(name="hist-graph-link-visible")
    run = db.create_run(pipeline.id)
    db.finish_run(run.id, status="FAILED", failed_step_key="fails")

    view = HistoryView()

    assert _has_graph_link_button(view, 0)


def test_open_graph_opens_dialog_with_pipeline_and_highlight(qapp, test_db, monkeypatch):
    from ui.main_window.history_view import HistoryView

    pipeline = db.create_pipeline(name="hist-graph-link-open")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "prod"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "fails"}},
    ], edges=[
        {"from_step_key": "prod", "from_port": "output_file", "to_step_key": "fails", "to_port": "input"},
    ])
    run = db.create_run(pipeline.id)
    db.finish_run(run.id, status="FAILED", failed_step_key="fails")

    view = HistoryView()

    captured = {}

    class _FakeGraphDialog:
        def __init__(self, parent, pipeline, highlight_step_key=None):
            captured["pipeline_id"] = pipeline.id
            captured["highlight_step_key"] = highlight_step_key

        def exec(self):
            captured["exec_called"] = True

    monkeypatch.setattr(
        "ui.graph_editor.PipelineGraphEditorDialog", _FakeGraphDialog,
    )

    view._open_graph(0)

    assert captured["pipeline_id"] == pipeline.id
    assert captured["highlight_step_key"] == "fails"
    assert captured["exec_called"] is True


def test_open_graph_out_of_range_row_does_not_raise(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    view = HistoryView()
    view._open_graph(999)   # ne doit pas lever
