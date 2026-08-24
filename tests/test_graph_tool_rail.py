"""
DataScheduler — tests/test_graph_tool_rail.py
Rail d'icônes flottant du canevas (chantier chrome de l'éditeur — refonte visuelle de la barre
d'outils qui débordait/se tronquait). Vérifie le câblage bouton → gestionnaire (déjà testé par
ailleurs, ici on vérifie juste que le CLIC réel atteint le bon gestionnaire), l'état visuel
actif/inactif du bouton mini-carte, et le décalage de départ qui dégage le rail des nœuds placés
par défaut.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
import pytest

from database import db_manager as db
from ui.graph_editor import PipelineGraphEditorDialog
from ui.graph_editor.graph_editor_dialog import _START_X, _START_Y


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_rail_repositions_without_crashing_on_empty_and_populated_scene(qapp, test_db):
    pipeline = db.create_pipeline(name="rail-reposition-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
    ], edges=[])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    dlg._rail.reposition()   # ne doit pas planter, scène peuplée

    empty_pipeline = db.create_pipeline(name="rail-reposition-empty-test")
    dlg2 = PipelineGraphEditorDialog(None, pipeline=empty_pipeline)
    dlg2._rail.reposition()   # ne doit pas planter, scène vide


def test_btn_undo_layout_is_the_same_widget_on_dialog_and_rail(qapp, test_db):
    """self._btn_undo_layout doit continuer d'exister et de répondre à isEnabled()/setEnabled()
    — seule dépendance directe des tests existants (test_graph_editor_dialog.py) sur un widget de
    la barre d'outils, désormais déplacé dans le rail."""
    pipeline = db.create_pipeline(name="rail-undo-identity-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    assert dlg._btn_undo_layout is dlg._rail.btn_undo_layout
    assert not dlg._btn_undo_layout.isEnabled()


def test_rail_add_step_button_click_opens_step_chooser(qapp, test_db, monkeypatch):
    from PySide6.QtWidgets import QDialog
    import ui.graph_editor.graph_editor_dialog as dialog_module

    pipeline = db.create_pipeline(name="rail-add-step-click-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    opened = []

    class _FakeChooser:
        def exec(self):
            opened.append(True)
            return QDialog.Rejected

    monkeypatch.setattr(dialog_module, "StepTypeChooserDialog", lambda *a, **k: _FakeChooser())

    dlg._rail.btn_add_step.click()

    assert opened == [True]


def test_rail_add_zone_button_click_creates_a_zone(qapp, test_db):
    pipeline = db.create_pipeline(name="rail-add-zone-click-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    dlg._rail.btn_add_zone.click()

    assert len(dlg._scene.zones) == 1


def test_rail_delete_button_click_removes_selected_node(qapp, test_db):
    pipeline = db.create_pipeline(name="rail-delete-click-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    node = dlg._scene.add_node({"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
                                dlg._next_new_node_pos())
    node.setSelected(True)

    dlg._rail.btn_delete.click()

    assert dlg._scene.nodes == {}


def test_rail_auto_layout_button_click_repositions_nodes(qapp, test_db):
    pipeline = db.create_pipeline(name="rail-auto-layout-click-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    before = {k: (n.pos().x(), n.pos().y()) for k, n in dlg._scene.nodes.items()}

    dlg._rail.btn_auto_layout.click()

    assert {k: (n.pos().x(), n.pos().y()) for k, n in dlg._scene.nodes.items()} != before
    assert dlg._btn_undo_layout.isEnabled()


def test_rail_arrange_selection_button_click_moves_only_selected_node(qapp, test_db):
    pipeline = db.create_pipeline(name="rail-arrange-selection-click-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    pos_a_before = dlg._scene.nodes["a"].pos()
    dlg._scene.nodes["b"].setSelected(True)

    dlg._rail.btn_arrange_selection.click()

    assert dlg._scene.nodes["a"].pos() == pos_a_before
    assert dlg._btn_undo_layout.isEnabled()


def test_rail_undo_layout_button_click_restores_positions(qapp, test_db):
    pipeline = db.create_pipeline(name="rail-undo-layout-click-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    before = {k: (n.pos().x(), n.pos().y()) for k, n in dlg._scene.nodes.items()}

    dlg._rail.btn_auto_layout.click()
    dlg._rail.btn_undo_layout.click()

    assert {k: (n.pos().x(), n.pos().y()) for k, n in dlg._scene.nodes.items()} == before


def test_rail_help_button_click_opens_help_dialog(qapp, test_db, monkeypatch):
    from PySide6.QtWidgets import QDialog
    import ui.graph_editor.graph_editor_dialog as dialog_module

    pipeline = db.create_pipeline(name="rail-help-click-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    opened = []

    class _FakeHelpDialog:
        def __init__(self, topic, parent=None):
            opened.append(topic.key)

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(dialog_module, "GraphHelpDialog", _FakeHelpDialog)

    dlg._rail.btn_help.click()

    assert opened == ["graph-editor"]


def test_rail_toggle_minimap_button_click_flips_visibility(qapp, test_db):
    pipeline = db.create_pipeline(name="rail-toggle-minimap-click-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    assert not dlg._minimap.isHidden()

    dlg._rail.btn_toggle_minimap.click()
    assert dlg._minimap.isHidden()

    dlg._rail.btn_toggle_minimap.click()
    assert not dlg._minimap.isHidden()


def test_schedule_button_click_reaches_the_handler(qapp, test_db, monkeypatch):
    """Le bouton "Planification & déclenchement…" reste un bouton texte dans la barre du haut
    (pas dans le rail) — le comportement complet de _on_open_schedule_dialog() est déjà couvert
    par test_schedule_button_opens_linear_editor_and_refreshes_title
    (tests/test_graph_editor_dialog.py) ; ici on vérifie juste que le clic RÉEL sur le bouton
    atteint bien ce gestionnaire, pas seulement l'appel direct de la méthode."""
    from PySide6.QtWidgets import QDialog, QPushButton
    import ui.step_editor as step_editor_module

    pipeline = db.create_pipeline(name="rail-schedule-click-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    opened = []

    class _FakeEditor:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            opened.append(True)
            return QDialog.Rejected

    monkeypatch.setattr(step_editor_module, "PipelineEditorDialog", _FakeEditor)

    schedule_btn = next(
        b for b in dlg.findChildren(QPushButton) if "Planification" in b.text()
    )
    schedule_btn.click()

    assert opened == [True]


# ──────────────────────────────────────────────
#  État visuel actif/inactif du bouton mini-carte
# ──────────────────────────────────────────────

def test_minimap_button_starts_styled_active_since_minimap_is_visible_by_default(qapp, test_db):
    pipeline = db.create_pipeline(name="rail-minimap-btn-default-style-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    assert dlg._rail.btn_toggle_minimap.styleSheet() != ""


def test_minimap_button_style_clears_when_minimap_hidden(qapp, test_db):
    pipeline = db.create_pipeline(name="rail-minimap-btn-hide-style-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    dlg._on_toggle_minimap()

    assert dlg._rail.btn_toggle_minimap.styleSheet() == ""


def test_minimap_button_style_restored_when_shown_again(qapp, test_db):
    pipeline = db.create_pipeline(name="rail-minimap-btn-reshow-style-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    dlg._on_toggle_minimap()
    dlg._on_toggle_minimap()

    assert dlg._rail.btn_toggle_minimap.styleSheet() != ""


# ──────────────────────────────────────────────
#  Décalage de départ — dégage le rail des nœuds placés par défaut
# ──────────────────────────────────────────────

def test_start_position_constants_cleared_the_old_top_left_corner():
    """Non-régression : le rail flottant occupe le coin haut-gauche du canevas — si ces
    constantes revenaient un jour à 60/60 par erreur, le premier nœud d'un pipeline neuf (ou
    legacy jamais repositionné) se retrouverait à nouveau caché derrière le rail."""
    assert (_START_X, _START_Y) != (60, 60)
    assert _START_X >= 100
    assert _START_Y >= 80
