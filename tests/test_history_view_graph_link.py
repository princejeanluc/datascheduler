"""
DataScheduler — tests/test_history_view_graph_link.py
Chantier UX éditeur, Lot 1 (B1b) : bouton "Voir dans le graphe" sur une ligne d'historique en
échec — émet open_atelier_requested (chantier Atelier Pipelines) pour que MainWindow ouvre
l'Atelier avec le nœud fautif surligné. Visible seulement quand
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


def _row_of(view, run_id):
    """Index de ligne d'un run donné — plus robuste qu'une ligne fixe maintenant que le tableau
    principal entrelace des lignes d'en-tête de groupe de jour (A5, refonte lot A-Historique) :
    une seule exécution aujourd'hui est tout de même précédée de la ligne "AUJOURD'HUI"."""
    return view._run_ids.index(run_id)


def test_graph_link_hidden_for_a_successful_run(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    pipeline = db.create_pipeline(name="hist-graph-link-success")
    run = db.create_run(pipeline.id)
    db.finish_run(run.id, status="SUCCESS")

    view = HistoryView()

    assert not _has_graph_link_button(view, _row_of(view, run.id))


def test_graph_link_hidden_for_a_failed_run_without_step_key(qapp, test_db):
    """Échec survenu hors de la boucle d'étapes (pipeline introuvable, plafond de concurrence,
    exception générique) — pas de nœud à montrer, le bouton ne doit pas apparaître."""
    from ui.main_window.history_view import HistoryView

    pipeline = db.create_pipeline(name="hist-graph-link-no-key")
    run = db.create_run(pipeline.id)
    db.finish_run(run.id, status="FAILED", error_message="échec générique")

    view = HistoryView()

    assert not _has_graph_link_button(view, _row_of(view, run.id))


def test_graph_link_visible_for_a_failed_run_with_step_key(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    pipeline = db.create_pipeline(name="hist-graph-link-visible")
    run = db.create_run(pipeline.id)
    db.finish_run(run.id, status="FAILED", failed_step_key="fails")

    view = HistoryView()

    assert _has_graph_link_button(view, _row_of(view, run.id))


def test_open_graph_emits_open_atelier_run_requested_with_pipeline_run_and_highlight(qapp, test_db):
    """Chantier Atelier Pipelines : "Voir dans le graphe" ouvre désormais l'Atelier (vue
    non-modale intégrée à la fenêtre principale) plutôt qu'un PipelineGraphEditorDialog modal —
    HistoryView ne construit plus ce dialogue elle-même, elle émet un signal que MainWindow
    écoute. C9 (Atelier-echec) : émet désormais open_atelier_run_requested (avec l'id du run, pas
    seulement le step_key) pour que l'Atelier affiche la vue riche d'exécution — plus l'ancien
    open_atelier_requested, dont la vue d'un seul nœud surligné n'est qu'un repli sans données B1
    (voir ui/main_window/window.py::open_atelier_run)."""
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
    captured = []
    view.open_atelier_run_requested.connect(lambda *args: captured.append(args))

    view._open_graph(_row_of(view, run.id))

    assert captured == [(pipeline.id, run.id, "fails")]


def test_open_graph_out_of_range_row_does_not_raise(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    view = HistoryView()
    view._open_graph(999)   # ne doit pas lever
