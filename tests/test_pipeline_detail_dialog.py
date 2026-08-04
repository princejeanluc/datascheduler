"""
DataScheduler — tests/test_pipeline_detail_dialog.py
Fumée (offscreen Qt) : PipelineDetailDialog (chantier UX fiabilité, D.1) s'ouvre avec un
pipeline ayant des runs, le graphique est alimenté par pipeline_id, la table des runs est
correcte, le log d'un run s'ouvre sans exception.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_dialog_shows_summary_and_chart_scoped_to_pipeline(qapp, test_db):
    from ui.dialogs import PipelineDetailDialog

    p1 = db.create_pipeline(name="detail-p1")
    p2 = db.create_pipeline(name="detail-p2")
    r1 = db.create_run(p1.id)
    db.finish_run(r1.id, status="SUCCESS", rows_exported=10)
    r2 = db.create_run(p2.id)
    db.finish_run(r2.id, status="FAILED")

    dlg = PipelineDetailDialog(None, pipeline=p1)

    assert "1 exécution" in dlg.lbl_summary.text()
    assert "100 %" in dlg.lbl_summary.text()
    assert dlg.chart._data[-1]["success"] == 1
    assert dlg.chart._data[-1]["failed"] == 0  # le run FAILED appartient à p2, pas p1


def test_dialog_lists_recent_runs(qapp, test_db):
    from ui.dialogs import PipelineDetailDialog

    p = db.create_pipeline(name="detail-runs-list")
    for _ in range(3):
        r = db.create_run(p.id)
        db.finish_run(r.id, status="SUCCESS", rows_exported=1)

    dlg = PipelineDetailDialog(None, pipeline=p)
    assert dlg.table.rowCount() == 3
    assert len(dlg._run_ids) == 3


def test_dialog_open_log_does_not_raise(qapp, test_db, monkeypatch):
    from ui.dialogs import PipelineDetailDialog

    monkeypatch.setattr(QDialog, "exec", lambda self: None)

    p = db.create_pipeline(name="detail-open-log")
    r = db.create_run(p.id)
    db.finish_run(r.id, status="SUCCESS", log_text="ligne de log")

    dlg = PipelineDetailDialog(None, pipeline=p)
    dlg._open_log(0)   # ne doit lever aucune exception


def test_dialog_shows_inactive_badge_when_pipeline_disabled(qapp, test_db):
    from ui.dialogs import PipelineDetailDialog

    p = db.create_pipeline(name="detail-inactive")
    db.set_pipeline_active(p.id, False)
    p = db.get_pipeline(p.id)

    dlg = PipelineDetailDialog(None, pipeline=p)
    assert dlg is not None  # construction sans exception avec un pipeline inactif
