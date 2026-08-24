"""
DataScheduler — tests/test_graph_minimap.py
Mini-carte de navigation (chantier UX éditeur, Lot 2, A3). Les fonctions de mapping sont pures
(tuples, pas de peinture réelle) — le smoke test du widget (repaint sur scène vide/peuplée,
navigation) suit le même réflexe que test_resources_view.py::test_time_series_chart_* (resize()
+ repaint(), offscreen Qt).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication
import pytest

from database import db_manager as db
from ui.graph_editor import PipelineGraphEditorDialog
from ui.graph_editor.minimap_widget import (
    GraphMinimapWidget, _minimap_target_rect, _scene_point_to_minimap,
    _scene_rect_to_minimap, _minimap_point_to_scene,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ──────────────────────────────────────────────
#  Fonctions de mapping pures
# ──────────────────────────────────────────────

def test_minimap_target_rect_is_inset_by_margin():
    x, y, w, h = _minimap_target_rect(180, 130, margin=2)
    assert (x, y) == (2, 2)
    assert (w, h) == (176, 126)


def test_minimap_target_rect_never_degenerates_on_tiny_widget():
    _, _, w, h = _minimap_target_rect(2, 2, margin=2)
    assert w >= 1.0 and h >= 1.0


def test_scene_point_to_minimap_maps_corners():
    source = (0, 0, 1000, 500)
    target = (0, 0, 100, 50)
    assert _scene_point_to_minimap(0, 0, source, target) == (0, 0)
    assert _scene_point_to_minimap(1000, 500, source, target) == (100, 50)
    assert _scene_point_to_minimap(500, 250, source, target) == (50, 25)


def test_scene_point_to_minimap_degenerate_source_falls_back_to_target_origin():
    source = (10, 10, 0, 0)
    target = (2, 2, 176, 126)
    assert _scene_point_to_minimap(999, 999, source, target) == (2, 2)


def test_scene_rect_to_minimap_round_trips_scale():
    source = (0, 0, 1000, 500)
    target = (0, 0, 100, 50)
    x, y, w, h = _scene_rect_to_minimap((100, 100, 200, 100), source, target)
    assert (x, y, w, h) == (10, 10, 20, 10)


def test_minimap_point_to_scene_is_the_inverse_of_scene_point_to_minimap():
    source = (0, 0, 1000, 500)
    target = (0, 0, 100, 50)
    mx, my = _scene_point_to_minimap(300, 150, source, target)
    sx, sy = _minimap_point_to_scene(mx, my, source, target)
    assert (sx, sy) == pytest.approx((300, 150))


def test_minimap_point_to_scene_returns_none_on_empty_source():
    assert _minimap_point_to_scene(10, 10, (0, 0, 0, 0), (0, 0, 100, 50)) is None


def test_minimap_point_to_scene_returns_none_on_degenerate_target():
    assert _minimap_point_to_scene(10, 10, (0, 0, 100, 50), (0, 0, 0, 0)) is None


# ──────────────────────────────────────────────
#  Widget — fumée (offscreen Qt, comme test_resources_view.py)
# ──────────────────────────────────────────────

def test_minimap_widget_repaints_without_crashing_on_empty_scene(qapp, test_db):
    pipeline = db.create_pipeline(name="minimap-empty-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    dlg._minimap.resize(180, 130)
    dlg._minimap.repaint()   # scène sans étape — ne doit pas planter (garde itemsBoundingRect vide)


def test_minimap_widget_repaints_without_crashing_on_populated_scene(qapp, test_db):
    pipeline = db.create_pipeline(name="minimap-populated-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
    ])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    dlg._minimap.resize(180, 130)
    dlg._minimap.repaint()


def test_toggle_minimap_button_flips_visibility(qapp, test_db):
    """isHidden() plutôt que isVisible() : ce dernier dépend aussi de la visibilité des parents,
    donc pas fiable tant que le dialogue n'est pas réellement affiché (voir
    tests/test_step_type_chooser.py, même convention)."""
    pipeline = db.create_pipeline(name="minimap-toggle-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    assert not dlg._minimap.isHidden()

    dlg._on_toggle_minimap()
    assert dlg._minimap.isHidden()

    dlg._on_toggle_minimap()
    assert not dlg._minimap.isHidden()


def test_minimap_navigate_centers_view_on_mapped_scene_point(qapp, test_db, monkeypatch):
    pipeline = db.create_pipeline(name="minimap-navigate-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}},
    ], edges=[])
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    centered = []
    monkeypatch.setattr(dlg._view, "centerOn", lambda pt: centered.append(pt))

    dlg._minimap._navigate(QPointF(90, 65))

    assert len(centered) == 1
    assert isinstance(centered[0], QPointF)


def test_minimap_navigate_is_a_no_op_on_empty_scene(qapp, test_db, monkeypatch):
    pipeline = db.create_pipeline(name="minimap-navigate-empty-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    centered = []
    monkeypatch.setattr(dlg._view, "centerOn", lambda pt: centered.append(pt))

    dlg._minimap._navigate(QPointF(90, 65))

    assert centered == []
