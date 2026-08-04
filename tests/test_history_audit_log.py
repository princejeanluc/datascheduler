"""
DataScheduler — tests/test_history_audit_log.py
Fumée (offscreen Qt) : le "Journal des modifications" de la vue Historique (chantier UX
post-personas, item 3 couche 3 — persona "Nadia") affiche bien les AuditEvent en base, sans
avoir à ouvrir la base SQLite à la main.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_audit_table_lists_events_most_recent_first(qapp, test_db):
    from database import db_manager as db
    from ui.main_window.history_view import HistoryView

    db.log_audit_event("pipeline_created", pipeline_id=1, pipeline_name="p1", detail="détail 1")
    db.log_audit_event("pipeline_edited", pipeline_id=1, pipeline_name="p1", detail="détail 2")

    events = db.get_audit_events()
    table = HistoryView._build_audit_table(events)

    assert table.rowCount() == 2
    assert table.item(0, 1).text() == "pipeline_edited"
    assert table.item(0, 2).text() == "p1"
    assert table.item(0, 4).text() == "détail 2"
    assert table.item(1, 1).text() == "pipeline_created"


def test_audit_table_handles_missing_optional_fields(qapp, test_db):
    from database import db_manager as db
    from ui.main_window.history_view import HistoryView

    db.log_audit_event("pipeline_deleted")

    events = db.get_audit_events()
    table = HistoryView._build_audit_table(events)

    assert table.item(0, 2).text() == "—"
    assert table.item(0, 4).text() == "—"


def test_audit_table_empty_when_no_events(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    table = HistoryView._build_audit_table([])
    assert table.rowCount() == 0


def test_history_view_has_audit_log_button(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    view = HistoryView()
    assert hasattr(view, "_on_audit_log")
