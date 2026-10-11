"""
DataScheduler — tests/test_atelier_pipelines_view.py
AtelierPipelinesView (chantier Atelier Pipelines, écran 2) : assemblage sidebar/canevas/panneau,
gestion du polling d'exécution, règles spécifiques au flux "+ Nouveau pipeline"
(is_new_pipeline=True — planification au premier enregistrement du graphe, suppression de la
coquille vide au retour sans étape). Construit directement, sans MainWindow — même raison que
tests/test_nav_rail_collapse.py (effets de bord réels dans MainWindow.__init__, voir sa docstring).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _pipeline_with_step(name="atelier-view-test"):
    p = db.create_pipeline(name=name)
    db.save_pipeline_graph(p.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
    ], edges=[])
    return p


def test_constructs_without_pipeline_without_raising(qapp, test_db):
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    view = AtelierPipelinesView()
    assert view._canvas is None
    assert view._settings_panel is None


def test_open_pipeline_builds_canvas_and_settings_panel(qapp, test_db):
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    p = _pipeline_with_step()
    view = AtelierPipelinesView()
    view.open_pipeline(p.id)

    assert view._canvas is not None
    assert view._settings_panel is not None
    assert view._pipeline_id == p.id
    assert view._title_lbl.text() == p.name
    # Le bouton "Paramètres du pipeline" de la toolbar du canevas est redondant une fois le
    # panneau de droite toujours visible — voir show_settings_shortcut_button.
    assert view._canvas._show_settings_shortcut_button is False


def test_open_pipeline_selects_the_row_in_the_sidebar(qapp, test_db):
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    p = _pipeline_with_step()
    view = AtelierPipelinesView()
    view.open_pipeline(p.id)

    assert view._sidebar._active_id == p.id


def test_open_pipeline_with_unknown_id_shows_placeholder_without_raising(qapp, test_db):
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    view = AtelierPipelinesView()
    view.open_pipeline(999999)

    assert view._canvas is None
    assert view._pipeline_id is None


def test_switching_pipeline_stops_polling_on_the_previous_canvas(qapp, test_db):
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    p1 = _pipeline_with_step("atelier-switch-1")
    p2 = _pipeline_with_step("atelier-switch-2")
    view = AtelierPipelinesView()
    view.open_pipeline(p1.id)
    old_canvas = view._canvas
    assert old_canvas._executing_timer.isActive()

    view.open_pipeline(p2.id)

    # stop_polling() remet l'attribut à None plutôt que de laisser un QTimer arrêté qui existe
    # encore (même convention que start_polling()/l'absence totale de l'attribut avant le
    # premier appel — voir graph_editor_widget.py).
    assert getattr(old_canvas, "_executing_timer", None) is None
    assert view._canvas is not old_canvas
    assert view._pipeline_id == p2.id


def test_highlight_step_key_skips_polling_on_open(qapp, test_db):
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    p = _pipeline_with_step()
    view = AtelierPipelinesView()
    view.open_pipeline(p.id, highlight_step_key="a")

    assert not hasattr(view._canvas, "_executing_timer")


def test_refresh_never_touches_the_open_canvas_or_panel(qapp, test_db):
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    p = _pipeline_with_step()
    view = AtelierPipelinesView()
    view.open_pipeline(p.id)
    canvas_before, panel_before = view._canvas, view._settings_panel

    view.refresh()

    assert view._canvas is canvas_before
    assert view._settings_panel is panel_before


def test_back_requested_is_emitted_and_polling_stopped(qapp, test_db):
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    p = _pipeline_with_step()
    view = AtelierPipelinesView()
    view.open_pipeline(p.id)
    captured = []
    view.back_requested.connect(lambda: captured.append(True))

    view._on_back_clicked()

    assert captured == [True]
    assert getattr(view._canvas, "_executing_timer", None) is None


def test_back_on_a_plain_edit_never_deletes_the_pipeline_even_with_zero_steps(qapp, test_db):
    """is_new_pipeline=False (défaut) — la règle "coquille vide supprimée au retour" ne doit
    jamais s'appliquer à une simple édition, même si le pipeline édité se trouve avoir 0 étape."""
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    p = db.create_pipeline(name="atelier-plain-edit-zero-steps")
    view = AtelierPipelinesView()
    view.open_pipeline(p.id, is_new_pipeline=False)

    view._on_back_clicked()

    assert db.get_pipeline(p.id) is not None


def test_new_pipeline_back_without_any_step_deletes_the_shell(qapp, test_db):
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    p = db.create_pipeline(name="atelier-new-pipeline-shell")
    view = AtelierPipelinesView()
    view.open_pipeline(p.id, is_new_pipeline=True)

    view._on_back_clicked()

    assert db.get_pipeline(p.id) is None


def test_new_pipeline_back_with_a_step_keeps_the_pipeline(qapp, test_db):
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    p = _pipeline_with_step("atelier-new-pipeline-with-step")
    view = AtelierPipelinesView()
    view.open_pipeline(p.id, is_new_pipeline=True)

    view._on_back_clicked()

    assert db.get_pipeline(p.id) is not None


def test_new_pipeline_schedules_once_the_graph_is_first_saved(qapp, test_db, monkeypatch):
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView
    import ui.main_window.pipelines_view as pipelines_view_module
    from PySide6.QtCore import QPointF

    p = db.create_pipeline(name="atelier-new-pipeline-schedule")
    view = AtelierPipelinesView()
    view.open_pipeline(p.id, is_new_pipeline=True)

    scheduled = []
    monkeypatch.setattr(
        pipelines_view_module.PipelinesView, "_schedule_if_possible",
        staticmethod(lambda pid: scheduled.append(pid)),
    )

    # Un graphe vide ne s'enregistre jamais (voir PipelineGraphEditorWidget.save()) — il faut au
    # moins une étape pour que `saved` ait une chance de s'émettre.
    view._canvas._scene.add_node({"step_type": "DB_EXTRACT", "config": {"_step_key": "x"}},
                                  QPointF(0, 0))
    assert view._canvas.save() is True

    assert scheduled == [p.id]


def test_plain_edit_never_schedules_on_graph_save(qapp, test_db, monkeypatch):
    """is_new_pipeline=False (défaut) — contrairement au flux "+ Nouveau pipeline", une simple
    édition du graphe ne doit jamais déclencher de replanification implicite (même comportement
    que l'ancien _on_edit_pipeline_graph(), qui ne replanifiait jamais)."""
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView
    import ui.main_window.pipelines_view as pipelines_view_module
    from PySide6.QtCore import QPointF

    p = _pipeline_with_step("atelier-plain-edit-no-schedule")
    view = AtelierPipelinesView()
    view.open_pipeline(p.id, is_new_pipeline=False)

    scheduled = []
    monkeypatch.setattr(
        pipelines_view_module.PipelinesView, "_schedule_if_possible",
        staticmethod(lambda pid: scheduled.append(pid)),
    )

    view._canvas._scene.add_node({"step_type": "DB_EXTRACT", "config": {"_step_key": "y"}},
                                  QPointF(200, 0))
    assert view._canvas.save() is True

    assert scheduled == []


def test_selecting_a_pipeline_in_the_sidebar_opens_it(qapp, test_db):
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    p1 = _pipeline_with_step("atelier-sidebar-select-1")
    p2 = _pipeline_with_step("atelier-sidebar-select-2")
    view = AtelierPipelinesView()
    view.open_pipeline(p1.id)
    view.refresh()   # peuple la sidebar avec les pipelines existants

    view._sidebar.pipeline_selected.emit(p2.id)

    assert view._pipeline_id == p2.id
