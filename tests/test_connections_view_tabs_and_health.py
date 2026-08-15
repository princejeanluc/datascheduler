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
    # Colonne 5, pas 4 : "Via" (bastion, chantier M) s'est insérée avant "État".
    badge = view.ssh_table.cellWidget(0, 5)
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


def test_connection_indicator_colors_by_success_state(qapp):
    """"Prise" vivante (chantier identité, vague 2, idée 10) — icône ajoutée à côté du badge
    texte existant, jamais à sa place (décision confirmée avec l'utilisateur)."""
    from ui.main_window.connections_view import _connection_indicator

    assert not _connection_indicator(True).pixmap().isNull()
    assert not _connection_indicator(False).pixmap().isNull()
    assert not _connection_indicator(None).pixmap().isNull()


def test_ssh_table_has_a_connection_indicator_column_alongside_the_text_badge(qapp, test_db):
    """La nouvelle colonne s'ajoute — _health_badge() et sa colonne "État" restent inchangés,
    la colonne Actions se décale automatiquement (voir _make_table)."""
    from ui.main_window.connections_view import ConnectionsView

    p = db.create_ssh_profile(name="EDGE01", host="h", port=22, username="u", password="pw")
    db.record_profile_test_result("ssh", p.id, True)

    view = ConnectionsView()
    badge = view.ssh_table.cellWidget(0, 5)
    indicator = view.ssh_table.cellWidget(0, 6)
    actions = view.ssh_table.cellWidget(0, 7)

    assert badge.text() == "OK"           # inchangé
    assert indicator is not None          # nouvelle colonne, juste après "État"
    assert actions is not None            # colonne Actions décalée, toujours présente


def test_health_badge_dims_a_profile_not_retested_recently(qapp, test_db):
    """Fraîcheur visuelle (chantier identité, vague 1, idée 11) — un profil testé il y a plus de
    30 jours s'estompe (effet d'opacité) pour signaler qu'il mérite d'être revérifié ; un profil
    testé récemment reste net."""
    from datetime import datetime, timedelta

    from ui.main_window.connections_view import ConnectionsView

    fresh = db.create_ssh_profile(name="EDGE-FRESH", host="h1", port=22, username="u", password="pw")
    stale = db.create_ssh_profile(name="EDGE-STALE", host="h2", port=22, username="u", password="pw")
    db.record_profile_test_result("ssh", fresh.id, True)
    db.record_profile_test_result("ssh", stale.id, True)
    with db.get_session() as s:
        from database.models import SshProfile
        obj = s.get(SshProfile, stale.id)
        obj.last_tested_at = datetime.utcnow() - timedelta(days=40)

    view = ConnectionsView()
    rows = {view.ssh_table.item(r, 0).text(): r for r in range(view.ssh_table.rowCount())}
    fresh_badge = view.ssh_table.cellWidget(rows["EDGE-FRESH"], 5)
    stale_badge = view.ssh_table.cellWidget(rows["EDGE-STALE"], 5)

    assert fresh_badge.graphicsEffect() is None
    assert stale_badge.graphicsEffect() is not None
    assert "revérifier" in stale_badge.toolTip()


def test_search_filters_across_active_tab_tables(qapp, test_db):
    from ui.main_window.connections_view import ConnectionsView

    db.create_ssh_profile(name="EDGE-ALPHA", host="h1", port=22, username="u", password="pw")
    db.create_ssh_profile(name="EDGE-BETA", host="h2", port=22, username="u", password="pw")

    view = ConnectionsView()
    view.inp_search.setText("alpha")

    assert not view.ssh_table.isRowHidden(0)
    assert view.ssh_table.isRowHidden(1)
