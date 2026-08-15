"""
DataScheduler — tests/test_pipelines_view_refresh_skips_open_menu.py
Bug réel signalé par l'utilisateur : laisser le menu "⋯" d'une ligne ouvert pendant qu'un
rafraîchissement automatique survient (timer périodique, 30s) faisait planter l'application —
refresh() reconstruit toute la colonne Actions (donc chaque QMenu) à chaque appel, y compris un
menu actuellement affiché, dont la boucle d'événements imbriquée ne survit pas à la destruction
de son widget sous-jacent. Repéré en pratique après l'ajout de l'action "Interrompre l'exécution
en cours" (conditionnelle à l'état RUNNING), qui donnait une vraie raison de laisser le menu
ouvert en observant la transition d'état — mais le risque structurel préexistait déjà.
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


def test_refresh_skips_rebuild_while_a_popup_menu_is_active(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    db.create_pipeline(name="popup-guard-test")
    view = PipelinesView()
    assert view.table.rowCount() == 1

    db.create_pipeline(name="popup-guard-test-2")
    monkeypatch.setattr(QApplication, "activePopupWidget", staticmethod(lambda: object()))

    view.refresh()

    # Le second pipeline n'apparaît pas : refresh() a été court-circuité avant de reconstruire
    # la table (donc avant de détruire le QMenu potentiellement affiché).
    assert view.table.rowCount() == 1


def test_refresh_rebuilds_normally_once_no_popup_is_active(qapp, test_db, monkeypatch):
    from ui.main_window.pipelines_view import PipelinesView

    db.create_pipeline(name="popup-guard-resume-test")
    view = PipelinesView()
    assert view.table.rowCount() == 1

    db.create_pipeline(name="popup-guard-resume-test-2")
    monkeypatch.setattr(QApplication, "activePopupWidget", staticmethod(lambda: None))

    view.refresh()

    assert view.table.rowCount() == 2
