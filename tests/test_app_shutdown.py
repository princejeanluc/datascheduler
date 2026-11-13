"""
DataScheduler — tests/test_app_shutdown.py
Lot D2-D4 (DONNEES.md::D4) : app_settings.last_closed_at, écrit par
ui/main_window/window.py::_write_last_closed_at — extraite de l'ancienne closure inline de
run() pour rester testable sans faire tourner une vraie boucle d'événements Qt (run() appelle
sys.exit(app.exec()), jamais invocable directement dans un test).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime, timedelta

from database import db_manager as db


def test_write_last_closed_at_sets_a_recent_utc_timestamp(test_db):
    from ui.main_window.window import _write_last_closed_at

    before = datetime.utcnow()
    _write_last_closed_at()
    after = datetime.utcnow()

    settings = db.get_app_settings()
    assert settings.last_closed_at is not None
    assert before - timedelta(seconds=1) <= settings.last_closed_at <= after + timedelta(seconds=1)


def test_last_closed_at_is_none_before_the_first_close(test_db):
    assert db.get_app_settings().last_closed_at is None
