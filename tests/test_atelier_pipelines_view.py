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


# ──────────────────────────────────────────────
#  Lot A-Atelier-main : en-tête (A6 fil d'Ariane, A7 Valider à blanc, A8 Exécuter)
# ──────────────────────────────────────────────

def test_header_stylesheet_is_qualified_not_a_bare_cascade_rule(qapp, test_db):
    """Régression réelle (constatée en capture, le bouton "Exécuter" rendu sans fond) — même
    piège déjà documenté et corrigé ailleurs (voir
    tests/test_queries_view_workshop.py::test_containers_use_qualified_stylesheet_selectors) :
    un style QSS brut sans sélecteur sur l'en-tête coupait la cascade de GLOBAL_STYLE pour tous
    ses boutons descendants sans objectName (fond accent attendu, par défaut)."""
    from PySide6.QtWidgets import QWidget
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    view = AtelierPipelinesView()
    header = view.findChild(QWidget, "atelierHeader")

    assert header is not None
    assert header.styleSheet().strip(), "en-tête : aucun style — pourquoi en poser un ?"
    assert "#atelierHeader" in header.styleSheet(), (
        f"en-tête : style non qualifié ({header.styleSheet()!r}) — "
        "couperait la cascade de GLOBAL_STYLE pour ses descendants."
    )


# ──────────────────────────────────────────────
#  Raccourci demandé par l'utilisateur : badge d'échec cliquable en édition normale
# ──────────────────────────────────────────────

def test_edit_mode_shows_a_clickable_failure_badge_when_a_resumable_run_exists(qapp, test_db):
    p = _pipeline_with_step("atelier-edit-badge")
    db.save_pipeline_graph(p.id, steps=[
        {"step_type": "FTP_UPLOAD", "label": "Déposer", "config": {"_step_key": "a"}},
    ], edges=[])
    run = db.create_run(p.id)
    db.finish_run(run.id, status="FAILED", failed_step_key="a", resumable_state_json="{}")

    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView
    view = AtelierPipelinesView()
    view.open_pipeline(p.id)

    assert view._run_badge is not None
    assert "Échec" in view._run_badge.text()
    assert "Déposer" in view._run_badge.text()
    # Les boutons d'édition normale restent affichés — ce badge est un raccourci en plus,
    # jamais un remplacement de l'en-tête habituel (contrairement à la vue d'un run).
    assert not view._btn_validate.isHidden()
    assert not view._btn_run.isHidden()


def test_edit_mode_has_no_failure_badge_without_a_resumable_run(qapp, test_db):
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    p = _pipeline_with_step("atelier-edit-badge-none")
    view = AtelierPipelinesView()
    view.open_pipeline(p.id)

    assert view._run_badge is None


def test_clicking_the_edit_mode_badge_opens_the_run_view(qapp, test_db):
    p = _pipeline_with_step("atelier-edit-badge-click")
    db.save_pipeline_graph(p.id, steps=[
        {"step_type": "FTP_UPLOAD", "label": "Déposer", "config": {"_step_key": "a"}},
    ], edges=[])
    run = db.create_run(p.id)
    db.finish_run(run.id, status="FAILED", failed_step_key="a", resumable_state_json="{}")

    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView
    view = AtelierPipelinesView()
    view.open_pipeline(p.id)

    view._run_badge.mouseReleaseEvent(None)

    assert view._run_id == run.id
    assert view._settings_normal_container.isHidden()
    assert not view._canvas.failure_panel.isHidden()


def test_breadcrumb_pipelines_click_triggers_the_same_back_behavior(qapp, test_db):
    """A6 : le fil d'Ariane "Pipelines" appelle _on_back_clicked, même comportement que l'ancien
    bouton "Retour aux pipelines" (suppression d'un pipeline neuf sans étape incluse)."""
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    p = db.create_pipeline(name="atelier-breadcrumb-shell")
    view = AtelierPipelinesView()
    view.open_pipeline(p.id, is_new_pipeline=True)

    emitted = []
    view.back_requested.connect(lambda: emitted.append(True))
    view._on_back_clicked()

    assert emitted == [True]
    assert db.get_pipeline(p.id) is None   # coquille sans étape supprimée


def test_validate_button_opens_pipeline_dry_run_dialog_for_the_open_pipeline(qapp, test_db, monkeypatch):
    """A7 : réutilise PipelineDryRunDialog (modal), orphelin côté PipelinesView mais explicitement
    demandé ici par la fiche Atelier. Import local (from ui.dialogs import ...) : le monkeypatch
    doit viser l'attribut sur ui.dialogs, pas sur le module atelier_pipelines_view."""
    import ui.dialogs as dialogs_module
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    p = _pipeline_with_step("atelier-validate-btn")
    view = AtelierPipelinesView()
    view.open_pipeline(p.id)

    calls = []
    monkeypatch.setattr(
        dialogs_module, "PipelineDryRunDialog",
        lambda pipeline_id, name, parent: calls.append((pipeline_id, name)) or _DummyExec(),
    )
    view._on_validate_pipeline()

    assert calls == [(p.id, p.name)]


def test_run_button_delegates_to_the_factored_run_pipeline_now(qapp, test_db, monkeypatch):
    """A8 : même chemin que depuis la liste des pipelines — pipeline_actions.run_pipeline_now,
    pas une réimplémentation locale."""
    from ui.main_window import atelier_pipelines_view as module

    p = _pipeline_with_step("atelier-run-btn")
    view = module.AtelierPipelinesView()
    view.open_pipeline(p.id)

    calls = []
    monkeypatch.setattr(module, "run_pipeline_now", lambda parent, pipeline_id: calls.append(pipeline_id))
    view._on_run_pipeline()

    assert calls == [p.id]


class _DummyExec:
    def exec(self):
        return None


# ──────────────────────────────────────────────
#  C7 : bascule du panneau de droite (paramètres ↔ aperçu de type d'étape)
# ──────────────────────────────────────────────

def test_opening_a_pipeline_shows_settings_and_hides_the_preview_panel(qapp, test_db):
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    p = _pipeline_with_step("atelier-panel-swap-initial")
    view = AtelierPipelinesView()
    view.open_pipeline(p.id)

    assert not view._settings_normal_container.isHidden()
    assert view._canvas.preview_panel.isHidden()


def test_opening_the_step_library_swaps_to_the_preview_panel(qapp, test_db):
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    p = _pipeline_with_step("atelier-panel-swap-open")
    view = AtelierPipelinesView()
    view.open_pipeline(p.id)

    view._canvas.open_step_library()

    assert view._settings_normal_container.isHidden()
    assert not view._canvas.preview_panel.isHidden()


def test_closing_the_step_library_swaps_back_to_settings(qapp, test_db):
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    p = _pipeline_with_step("atelier-panel-swap-close")
    view = AtelierPipelinesView()
    view.open_pipeline(p.id)
    view._canvas.open_step_library()

    view._canvas.close_step_library()

    assert not view._settings_normal_container.isHidden()
    assert view._canvas.preview_panel.isHidden()


def test_switching_pipeline_resets_to_the_settings_panel(qapp, test_db):
    """Changer de pipeline reconstruit tout le canevas (_clear_container) — le panneau "Ajouter"
    ne doit jamais rester ouvert sur le pipeline suivant."""
    from ui.main_window.atelier_pipelines_view import AtelierPipelinesView

    p1 = _pipeline_with_step("atelier-panel-swap-switch-1")
    p2 = _pipeline_with_step("atelier-panel-swap-switch-2")
    view = AtelierPipelinesView()
    view.open_pipeline(p1.id)
    view._canvas.open_step_library()

    view.open_pipeline(p2.id)

    assert not view._settings_normal_container.isHidden()
    assert view._canvas.preview_panel.isHidden()
