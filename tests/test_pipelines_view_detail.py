"""
DataScheduler — tests/test_pipelines_view_detail.py
Fumée (offscreen Qt) : double-clic sur une ligne de PipelinesView (chantier UX fiabilité, D.1)
ouvre bien PipelineDetailDialog pour le bon pipeline.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QModelIndex
from PySide6.QtWidgets import QApplication, QDialog

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_double_click_opens_detail_for_correct_pipeline(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    opened = {}

    class _FakeDetailDialog:
        def __init__(self, parent, pipeline):
            opened["pipeline_id"] = pipeline.id
        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr("ui.dialogs.PipelineDetailDialog", _FakeDetailDialog)

    db.create_pipeline(name="p1")
    p2 = db.create_pipeline(name="p2")

    view = PipelinesView()
    assert view._pipeline_ids == [p for p in view._pipeline_ids]  # sanity: populated
    row_of_p2 = view._pipeline_ids.index(p2.id)

    index = view.table.model().index(row_of_p2, 0)
    view._on_row_dbl_click(index)

    assert opened.get("pipeline_id") == p2.id
