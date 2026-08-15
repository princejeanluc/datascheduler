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


def test_day_runs_table_lists_runs_most_recent_first(qapp, test_db):
    """Détail d'une case du calendrier de fréquence (chantier identité, vague 4, idée 13)."""
    from database import db_manager as db
    from ui.main_window.history_view import HistoryView

    p = db.create_pipeline(name="day-detail-test")
    r1 = db.create_run(p.id)
    db.finish_run(r1.id, status="SUCCESS", rows_exported=100)
    r2 = db.create_run(p.id)
    db.finish_run(r2.id, status="FAILED")

    runs = db.get_runs(p.id)
    table = HistoryView._build_day_runs_table(runs)

    assert table.rowCount() == 2
    assert table.item(0, 2).text() == "—"   # r2 (le plus récent) — FAILED, pas de lignes


def test_on_frequency_day_clicked_opens_dialog_with_that_days_runs(qapp, test_db, monkeypatch):
    from datetime import date

    from PySide6.QtWidgets import QDialog
    from database import db_manager as db
    from ui.main_window.history_view import HistoryView

    p = db.create_pipeline(name="day-click-test")
    run = db.create_run(p.id)
    db.finish_run(run.id, status="SUCCESS")
    today = date.today()

    captured = {}
    monkeypatch.setattr(QDialog, "exec", lambda self: captured.setdefault("opened", True))

    view = HistoryView()
    view._on_frequency_day_clicked(p, today)
    assert captured.get("opened")


def test_on_frequency_day_clicked_no_op_when_day_has_no_runs(qapp, test_db, monkeypatch):
    """Aucune exécution ce jour-là — pas de fenêtre vide à ouvrir."""
    from datetime import date

    from PySide6.QtWidgets import QDialog
    from database import db_manager as db
    from ui.main_window.history_view import HistoryView

    p = db.create_pipeline(name="day-click-empty-test")

    captured = {}
    monkeypatch.setattr(QDialog, "exec", lambda self: captured.setdefault("opened", True))

    view = HistoryView()
    view._on_frequency_day_clicked(p, date.today())
    assert "opened" not in captured
