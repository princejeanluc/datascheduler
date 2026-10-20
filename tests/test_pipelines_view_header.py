"""
DataScheduler — tests/test_pipelines_view_header.py
Refonte, lot A-Pipelines : A1 (en-tête via make_page_header, surtitre dynamique, bouton avec
raccourci affiché).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_header_title_is_static_pipelines(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    view = PipelinesView()
    assert view.findChild(QLabel, "page_title").text() == "Pipelines"


def test_eyebrow_shows_total_and_active_counts(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    db.create_pipeline(name="actif-1")
    p2 = db.create_pipeline(name="actif-2")
    inactive = db.create_pipeline(name="inactif-1")
    db.set_pipeline_active(inactive.id, False)

    view = PipelinesView()
    view.refresh()

    assert view._eyebrow_lbl.text() == "3 PIPELINES · 2 ACTIFS"


def test_eyebrow_singular_agreement(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    db.create_pipeline(name="solo")

    view = PipelinesView()
    view.refresh()

    assert view._eyebrow_lbl.text() == "1 PIPELINE · 1 ACTIF"


def test_new_pipeline_button_shows_ctrl_n_hint_and_triggers_creation(qapp, test_db, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from ui.main_window.pipelines_view import PipelinesView

    view = PipelinesView()
    labels = [lbl.text() for lbl in view.findChildren(QLabel)]
    assert "+ Nouveau pipeline" in labels
    assert "Ctrl N" in labels

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("depuis-bouton", True)))
    captured = []
    view.open_atelier_requested.connect(lambda *a: captured.append(a))

    from PySide6.QtCore import QEvent, QPoint, Qt as Qt2
    from PySide6.QtGui import QMouseEvent
    btn = next(
        w for w in view.findChildren(QLabel) if w.text() == "+ Nouveau pipeline"
    ).parentWidget()
    ev = QMouseEvent(QEvent.MouseButtonRelease, QPoint(5, 5), Qt2.LeftButton, Qt2.LeftButton, Qt2.NoModifier)
    btn.mouseReleaseEvent(ev)

    assert len(captured) == 1
    assert captured[0][2] is True   # is_new_pipeline


def test_search_placeholder_no_longer_mentions_ctrl_n(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    view = PipelinesView()
    assert "Ctrl" not in view.inp_search.placeholderText()
