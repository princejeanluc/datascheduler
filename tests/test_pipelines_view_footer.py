"""
DataScheduler — tests/test_pipelines_view_footer.py
Refonte, lot A-Pipelines : A9 (pied de liste — légende + « actualisé il y a N s »).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from database import db_manager as db


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_footer_shows_trigger_legend(qapp, test_db):
    from PySide6.QtWidgets import QLabel
    from ui.main_window.pipelines_view import PipelinesView

    view = PipelinesView()
    labels = [lbl.text() for lbl in view.findChildren(QLabel)]
    assert any("se lance après un autre pipeline" in t for t in labels)


def test_footer_does_not_mention_gated_or_incorrect_legends(qapp, test_db):
    from PySide6.QtWidgets import QLabel
    from ui.main_window.pipelines_view import PipelinesView

    view = PipelinesView()
    labels = " ".join(lbl.text() for lbl in view.findChildren(QLabel))
    assert "clic sur la forme" not in labels   # C7, gated
    assert "ouvre l'Atelier" not in labels      # faux avec P10 (double-clic garde le détail)


def test_footer_refreshed_label_updates_after_refresh(qapp, test_db):
    from ui.main_window.pipelines_view import PipelinesView

    view = PipelinesView()
    assert view._footer_refreshed_lbl.text().startswith("actualisé")
    assert view._last_refresh_at is not None


def test_footer_timer_ticks_independently_of_full_refresh(qapp, test_db):
    """Le label "actualisé..." avance même sans rafraîchissement complet du tableau — timer
    séparé à 1000 ms (voir __init__)."""
    from datetime import datetime, timedelta
    from ui.main_window.pipelines_view import PipelinesView

    view = PipelinesView()
    view._last_refresh_at = datetime.utcnow() - timedelta(minutes=2)
    view._refresh_footer_label()
    assert "2 min" in view._footer_refreshed_lbl.text()
