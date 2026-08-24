"""
DataScheduler — tests/test_graph_zones.py
Zones de regroupement visuel (chantier UX éditeur, Lot 2, A4b) : géométrie pure de
l'en-tête/poignée de redimensionnement, cycle de vie scène (add_zone/remove_zone), renommage,
et round-trip sauvegarde/chargement dans le dialogue. Pas de simulation de drag souris réelle
(même réflexe que tests/test_graph_editor_dialog.py) — les interactions
scene.add_zone()/remove_zone() sont exercées directement.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QInputDialog
import pytest

from database import db_manager as db
from ui.graph_editor import PipelineGraphEditorDialog
from ui.graph_editor.zone_item import (
    ZoneItem, _zone_header_rect, _zone_handle_rect, _clamp_zone_size,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ──────────────────────────────────────────────
#  Géométrie pure
# ──────────────────────────────────────────────

def test_zone_header_rect_spans_full_width_at_fixed_height():
    x, y, w, h = _zone_header_rect(240)
    assert (x, y) == (0, 0)
    assert w == 240
    assert h == 22.0


def test_zone_handle_rect_sits_in_bottom_right_corner():
    x, y, w, h = _zone_handle_rect(240, 160)
    assert x == 240 - 10.0
    assert y == 160 - 10.0
    assert (w, h) == (10.0, 10.0)


def test_clamp_zone_size_enforces_minimum():
    assert _clamp_zone_size(10, 10) == (80.0, 60.0)
    assert _clamp_zone_size(300, 200) == (300, 200)


def test_clamp_zone_size_only_clamps_the_dimension_below_minimum():
    assert _clamp_zone_size(300, 10) == (300, 60.0)


# ──────────────────────────────────────────────
#  Cycle de vie (scène)
# ──────────────────────────────────────────────

def test_zone_item_bounding_rect_matches_constructor_size(qapp):
    zone = ZoneItem("Ma zone", width=300, height=200)
    rect = zone.boundingRect()
    assert (rect.width(), rect.height()) == (300, 200)


def test_add_zone_registers_in_scene_zones_list(qapp, test_db):
    pipeline = db.create_pipeline(name="zone-add-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    zone = dlg._scene.add_zone("Extraction", QPointF(10, 20), 300, 200)

    assert dlg._scene.zones == [zone]
    assert zone.name == "Extraction"
    assert zone.pos() == QPointF(10, 20)


def test_remove_zone_unregisters_from_scene(qapp, test_db):
    pipeline = db.create_pipeline(name="zone-remove-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    zone = dlg._scene.add_zone("Zone 1", QPointF(0, 0))

    dlg._scene.remove_zone(zone)

    assert dlg._scene.zones == []


def test_on_add_zone_creates_a_zone_centered_on_the_viewport(qapp, test_db):
    pipeline = db.create_pipeline(name="zone-toolbar-add-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    dlg._on_add_zone()

    assert len(dlg._scene.zones) == 1
    assert dlg._scene.zones[0].name == "Nouvelle zone"


def test_on_zone_double_clicked_renames_on_confirm(qapp, test_db, monkeypatch):
    pipeline = db.create_pipeline(name="zone-rename-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    zone = dlg._scene.add_zone("Nouvelle zone", QPointF(0, 0))

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Ventes Q3", True)))
    dlg._on_zone_double_clicked(zone)

    assert zone.name == "Ventes Q3"


def test_on_zone_double_clicked_keeps_old_name_when_cancelled(qapp, test_db, monkeypatch):
    pipeline = db.create_pipeline(name="zone-rename-cancel-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    zone = dlg._scene.add_zone("Nouvelle zone", QPointF(0, 0))

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))
    dlg._on_zone_double_clicked(zone)

    assert zone.name == "Nouvelle zone"


def test_on_zone_double_clicked_rejects_empty_name(qapp, test_db, monkeypatch):
    pipeline = db.create_pipeline(name="zone-rename-empty-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    zone = dlg._scene.add_zone("Nouvelle zone", QPointF(0, 0))

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("   ", True)))
    dlg._on_zone_double_clicked(zone)

    assert zone.name == "Nouvelle zone"


def test_delete_selected_removes_a_selected_zone(qapp, test_db):
    pipeline = db.create_pipeline(name="zone-delete-selected-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    zone = dlg._scene.add_zone("Zone 1", QPointF(0, 0))
    zone.setSelected(True)

    dlg._on_delete_selected()

    assert dlg._scene.zones == []


# ──────────────────────────────────────────────
#  Round-trip sauvegarde/chargement
# ──────────────────────────────────────────────

def test_collect_graph_includes_zone_positions_and_size(qapp, test_db):
    pipeline = db.create_pipeline(name="zone-collect-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    dlg._scene.add_zone("Extraction", QPointF(10, 20), 300, 200)

    _, _, zones = dlg._collect_graph()

    assert zones == [{"name": "Extraction", "pos_x": 10, "pos_y": 20, "width": 300, "height": 200}]


def test_save_then_reload_round_trips_zones(qapp, test_db):
    pipeline = db.create_pipeline(name="zone-round-trip-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    dlg._scene.add_node(
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}}, QPointF(0, 0)
    )
    dlg._scene.add_zone("Extraction", QPointF(10, 20), 300, 200)

    dlg._on_save()

    reloaded = PipelineGraphEditorDialog(None, pipeline=db.get_pipeline(pipeline.id))
    assert len(reloaded._scene.zones) == 1
    zone = reloaded._scene.zones[0]
    assert zone.name == "Extraction"
    assert zone.pos() == QPointF(10, 20)
    assert (zone._width, zone._height) == (300, 200)
