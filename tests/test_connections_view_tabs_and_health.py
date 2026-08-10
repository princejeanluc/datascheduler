"""
DataScheduler — tests/test_connections_view_tabs_and_health.py
Fumée (offscreen Qt) : restructuration de ConnectionsView en onglets par usage, recherche
transverse, et badge d'état inline dérivé de last_test_success (chantier UX ergonomie, E.4) —
la critique UX/UI notait 5 panneaux empilés qui ne passaient pas à l'échelle, et un statut de
santé caché derrière la seule fenêtre modale "Bilan de santé".
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


def test_connections_view_has_three_tabs_grouped_by_usage(qapp, test_db):
    from ui.main_window.connections_view import ConnectionsView

    view = ConnectionsView()
    titles = [view.tabs.tabText(i) for i in range(view.tabs.count())]
    assert titles == ["Bases de données", "Fichiers && notifications", "Big Data / Spark SQL"]


def test_ssh_and_kerberos_panels_share_the_same_tab(qapp, test_db):
    from ui.main_window.connections_view import ConnectionsView

    view = ConnectionsView()
    bigdata_tab = view.tabs.widget(2)
    assert bigdata_tab.isAncestorOf(view.ssh_table)
    assert bigdata_tab.isAncestorOf(view.kerberos_table)
    # Chantier L : le panneau Élévation (sudo su, étape SQOOP_EXPORT) rejoint la même famille
    # "connexion edge" que SSH/Kerberos, pour la même raison qu'eux (toujours utilisés en paire).
    assert bigdata_tab.isAncestorOf(view.elevation_table)


@pytest.mark.parametrize("last_test_success,expected_text", [
    (True, "OK"),
    (False, "Échec"),
    (None, "Jamais testé"),
])
def test_ssh_health_badge_reflects_last_test_success(qapp, test_db, last_test_success, expected_text):
    from ui.main_window.connections_view import ConnectionsView

    p = db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="pw")
    if last_test_success is not None:
        db.record_profile_test_result("ssh", p.id, last_test_success)

    view = ConnectionsView()
    badge = view.ssh_table.cellWidget(0, 4)
    assert badge.text() == expected_text


@pytest.mark.parametrize("last_test_success,expected_text", [
    (True, "OK"),
    (False, "Échec"),
    (None, "Jamais testé"),
])
def test_elevation_health_badge_reflects_last_test_success(qapp, test_db, last_test_success, expected_text):
    from ui.main_window.connections_view import ConnectionsView

    p = db.create_elevation_profile(name="NIFI", target_user="nifi", password="pw")
    if last_test_success is not None:
        db.record_profile_test_result("elevation", p.id, last_test_success)

    view = ConnectionsView()
    badge = view.elevation_table.cellWidget(0, 2)
    assert badge.text() == expected_text


def test_database_health_badge_reflects_last_test_success(qapp, test_db):
    from ui.main_window.connections_view import ConnectionsView

    p = db.create_oracle_profile(name="ORA1", host="h", port=1521, service_name="s",
                                  username="u", password="pw")
    db.record_profile_test_result("oracle", p.id, True)

    view = ConnectionsView()
    badge = view.database_table.cellWidget(0, 5)
    assert badge.text() == "OK"


def test_search_filters_across_active_tab_tables(qapp, test_db):
    from ui.main_window.connections_view import ConnectionsView

    db.create_ssh_profile(name="EDGE-ALPHA", host="h1", port=22, username="u", password="pw")
    db.create_ssh_profile(name="EDGE-BETA", host="h2", port=22, username="u", password="pw")

    view = ConnectionsView()
    view.inp_search.setText("alpha")

    assert not view.ssh_table.isRowHidden(0)
    assert view.ssh_table.isRowHidden(1)
