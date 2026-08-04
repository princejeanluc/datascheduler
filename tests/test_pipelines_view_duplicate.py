"""
DataScheduler — tests/test_pipelines_view_duplicate.py
Fumée (offscreen Qt) : le bouton "Dupliquer" de PipelinesView (chantier UX autonomie, C.1) appelle
bien duplicate_pipeline() et rafraîchit la table. QMessageBox mocké — sinon .exec() bloque
indéfiniment en attendant un clic qui ne viendra jamais (voir test_pipeline_editor_dialog.py pour
le même précédent).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_duplicate_button_creates_new_row(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    p = db.create_pipeline(name="dup-view-test")
    db.save_steps(p.id, [{"step_type": "DB_EXTRACT", "config": {}}])

    view = PipelinesView()
    assert view.table.rowCount() == 1

    view._on_duplicate_pipeline(p.id)

    assert view.table.rowCount() == 2
    names = {pl.name for pl in db.get_pipelines()}
    assert "dup-view-test (copie)" in names


def test_duplicate_button_shows_error_on_failure(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    captured = {}

    def fake_critical(parent, title, text, *a, **k):
        captured["text"] = text

    monkeypatch.setattr(QMessageBox, "critical", staticmethod(fake_critical))

    view = PipelinesView()
    view._on_duplicate_pipeline(999)  # pipeline inexistant

    assert "text" in captured
