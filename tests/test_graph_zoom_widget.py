"""
DataScheduler — tests/test_graph_zoom_widget.py
Widget de zoom flottant (chantier identité visuelle) : +/- et le pourcentage courant, synchronisé
avec le zoom à la molette déjà existant.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication
import pytest

from database import db_manager as db
from ui.graph_editor import PipelineGraphEditorDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_zoom_widget_starts_at_100_percent(qapp, test_db):
    pipeline = db.create_pipeline(name="zoom-widget-default-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)
    assert dlg._zoom_widget.lbl_pct.text() == "100 %"


def test_zoom_in_button_increases_scale_and_updates_label(qapp, test_db):
    pipeline = db.create_pipeline(name="zoom-widget-in-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    dlg._zoom_widget.btn_zoom_in.click()

    assert dlg._view.transform().m11() > 1.0
    assert dlg._zoom_widget.lbl_pct.text() != "100 %"


def test_zoom_out_button_decreases_scale_and_updates_label(qapp, test_db):
    pipeline = db.create_pipeline(name="zoom-widget-out-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    dlg._zoom_widget.btn_zoom_out.click()

    assert dlg._view.transform().m11() < 1.0
    assert dlg._zoom_widget.lbl_pct.text() != "100 %"


def test_zoom_in_then_out_round_trips_back_to_100_percent(qapp, test_db):
    pipeline = db.create_pipeline(name="zoom-widget-roundtrip-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    dlg._zoom_widget.btn_zoom_in.click()
    dlg._zoom_widget.btn_zoom_out.click()

    assert dlg._view.transform().m11() == pytest.approx(1.0)


def test_mouse_wheel_zoom_also_refreshes_the_widget_label(qapp, test_db):
    pipeline = db.create_pipeline(name="zoom-widget-wheel-test")
    dlg = PipelineGraphEditorDialog(None, pipeline=pipeline)

    event = QWheelEvent(
        QPointF(50, 50), QPointF(50, 50), QPoint(0, 0), QPoint(0, 120),
        Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False,
    )
    dlg._view.wheelEvent(event)

    assert dlg._view.transform().m11() > 1.0
    assert dlg._zoom_widget.lbl_pct.text() != "100 %"
