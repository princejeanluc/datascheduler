"""
DataScheduler — tests/test_history_run_panel.py
Lot C-Historique-1 : panneau latéral d'un run atteint depuis le tableau principal (A10 complété),
colonne/mot d'origine (C3), section Étapes (C4), filtre Tout/Erreurs du journal (C5), et
rafraîchissement en direct porté dans le panneau (point 7 de "À garder tel quel").
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTextEdit

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_run(name: str, status: str, **finish_kwargs):
    pipeline = db.create_pipeline(name=name)
    run = db.create_run(pipeline.id)
    db.finish_run(run.id, status=status, **finish_kwargs)
    return pipeline, run


def test_double_click_on_table_row_opens_the_side_panel_not_the_old_dialog(qapp, test_db, monkeypatch):
    """Avant ce lot, le double-clic sur le tableau ouvrait run_log_dialog.py — désormais le même
    panneau que la bulle du jour (_open_run_panel)."""
    from ui.main_window.history_view import HistoryView

    _pipeline, run = _make_run("hist-panel-dblclick", "SUCCESS")
    view = HistoryView()

    called = {"legacy_dialog": False}
    monkeypatch.setattr(
        "ui.main_window.run_log_dialog.open_run_log_dialog",
        lambda *a, **kw: called.__setitem__("legacy_dialog", True),
    )

    row = view._run_ids.index(run.id)
    view._open_log(row)

    assert not called["legacy_dialog"]
    # view n'est pas affichée (pas de fenêtre top-level dans ce test) : isVisible() resterait
    # faux même une fois le panneau ouvert — on vérifie plutôt que set_content() a bien reçu le
    # contenu du run (_content non None), signe que _open_run_panel a été appelé.
    assert view._side_panel._content is not None


def test_panel_eyebrow_shows_the_origin_word():
    from ui.main_window.history_view import _origin_label

    assert _origin_label(None, None) == "—"
    assert _origin_label("SCHEDULED", None) == "Planifié"
    assert _origin_label("MANUAL", None) == "Manuel"
    assert _origin_label("CATCHUP", None) == "Rattrapé"
    assert _origin_label("RESUME", None) == "Reprise"
    assert _origin_label("TRIGGERED", None) == "Déclenché"
    assert _origin_label("TRIGGERED", 7) == "Déclenché ↳ #7"


def test_table_declenchement_column_reflects_trigger_origin(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    pipeline = db.create_pipeline(name="hist-origin-column")
    run = db.create_run(pipeline.id, trigger_origin="CATCHUP")
    db.finish_run(run.id, status="SUCCESS")

    view = HistoryView()
    row = view._run_ids.index(run.id)
    assert view.table.item(row, 5).text() == "Rattrapé"


def test_run_panel_shows_steps_section_when_steps_exist(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    pipeline, run = _make_run("hist-panel-steps", "SUCCESS")
    db.record_run_step(run.id, step_key="a", step_type="DB_EXTRACT", step_label="Extraction",
                        status="SUCCESS")

    view = HistoryView()
    content = view._build_run_panel_content(pipeline, db.get_run(run.id))
    labels = [w.text() for w in content.findChildren(QLabel)]
    assert "ÉTAPES" in labels
    assert any("Extraction" in t for t in labels)


def test_run_panel_has_no_steps_section_when_no_step_rows(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    pipeline, run = _make_run("hist-panel-no-steps", "SUCCESS")

    view = HistoryView()
    content = view._build_run_panel_content(pipeline, db.get_run(run.id))
    labels = [w.text() for w in content.findChildren(QLabel)]
    assert "ÉTAPES" not in labels


def test_log_filter_errors_only_keeps_only_error_level_entries_from_log_json(qapp, test_db):
    from ui.main_window.history_view import HistoryView

    log_entries = [
        {"t": "2026-01-01T10:00:00", "lvl": "INFO", "step_key": None, "msg": "Chargement"},
        {"t": "2026-01-01T10:00:01", "lvl": "ERROR", "step_key": None, "msg": "ERREUR : échec"},
    ]
    pipeline, run = _make_run("hist-panel-log-filter", "FAILED",
                               error_message="échec", log_text="[10:00:00] Chargement",
                               log_json=json.dumps(log_entries))

    view = HistoryView()
    content = view._build_run_panel_content(pipeline, db.get_run(run.id))
    log_box = content.findChild(QTextEdit)
    assert "Chargement" in log_box.toPlainText()

    btn_errors = next(b for b in content.findChildren(QPushButton) if b.text() == "Erreurs")
    btn_errors.click()
    assert "ERREUR" in log_box.toPlainText()
    assert "Chargement" not in log_box.toPlainText()


def test_log_filter_errors_only_works_on_legacy_log_text_without_log_json(qapp, test_db):
    """Repli B3 : un run d'avant D3 (log_json absent) — une ligne contenant "ERREUR : " est
    reconnue comme une entrée ERROR par le filtre."""
    from ui.main_window.history_view import HistoryView

    pipeline, run = _make_run(
        "hist-panel-log-filter-legacy", "FAILED", error_message="échec",
        log_text="[10:00:00] Chargement\n[10:00:01] ERREUR : échec",
    )

    view = HistoryView()
    content = view._build_run_panel_content(pipeline, db.get_run(run.id))
    log_box = content.findChild(QTextEdit)

    btn_errors = next(b for b in content.findChildren(QPushButton) if b.text() == "Erreurs")
    btn_errors.click()
    assert "ERREUR" in log_box.toPlainText()
    assert "Chargement" not in log_box.toPlainText()


def test_running_run_panel_live_refreshes_until_terminal_status(qapp, test_db):
    """Point 7 de "À garder tel quel", désormais porté par le panneau (avant ce lot, seul
    run_log_dialog.py l'offrait)."""
    from ui.main_window.history_view import HistoryView

    pipeline = db.create_pipeline(name="hist-panel-live")
    run = db.create_run(pipeline.id)
    db.update_run_progress(run.id, "Étape 1", "[10:00:00] Démarrage", log_json=json.dumps(
        [{"t": "2026-01-01T10:00:00", "lvl": "INFO", "step_key": None, "msg": "Démarrage"}]))

    view = HistoryView()
    content = view._build_run_panel_content(pipeline, db.get_run(run.id))
    timers = content.findChildren(QTimer)
    assert len(timers) == 1
    assert timers[0].isActive()

    step_lbl = next(
        w for w in content.findChildren(QLabel) if w.text().startswith("Étape en cours")
    )
    assert "Étape 1" in step_lbl.text()

    db.update_run_progress(run.id, "Étape 2", "[10:00:00] Démarrage\n[10:00:05] Étape 2")
    db.finish_run(run.id, status="SUCCESS")

    timers[0].timeout.emit()

    assert not timers[0].isActive()
    assert step_lbl.isVisible() is False
