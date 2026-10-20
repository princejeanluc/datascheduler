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
from PySide6.QtWidgets import QApplication, QLabel

from database import db_manager as db


def _cell_texts(table, row, col) -> list:
    """Libellés texte d'une cellule composite (refonte, lot A-Connexions : `_two_line_cell`/
    `_last_test_cell`) — exclut le point coloré (un QLabel vide, juste stylé en cercle)."""
    widget = table.cellWidget(row, col)
    return [lbl.text() for lbl in widget.findChildren(QLabel) if lbl.text()]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_connections_view_has_three_tabs_grouped_by_usage(qapp, test_db):
    from ui.main_window.connections_view import ConnectionsView

    view = ConnectionsView()
    titles = [view.tabs.tabText(i) for i in range(view.tabs.count())]
    assert titles == ["Bases de données", "Fichiers && notifications", "Big Data / Spark SQL"]


def test_connections_view_eyebrow_counts_connections_failures_and_never_tested(qapp, test_db):
    """A2 : surtitre dynamique, compté sur les 7 listes de profils — comptage côté vue, aucune
    nouvelle fonction de données."""
    from ui.main_window.connections_view import ConnectionsView

    ok = db.create_ssh_profile(name="EDGE-OK", host="h1", port=22, username="u", password="pw")
    db.record_profile_test_result("ssh", ok.id, True)
    failed = db.create_smtp_profile(name="SMTP-FAIL", host="h2", port=587, from_address="a@b.c")
    db.record_profile_test_result("smtp", failed.id, False)
    db.create_kerberos_profile(name="KRB-NEW", principal="p@REALM", password="pw")  # jamais testé

    view = ConnectionsView()
    assert view._eyebrow_lbl.text() == "3 CONNEXIONS · 1 EN ÉCHEC · 1 JAMAIS TESTÉE"


def test_connections_view_search_placeholder_matches_the_maquette(qapp, test_db):
    from ui.main_window.connections_view import ConnectionsView

    view = ConnectionsView()
    assert view.inp_search.placeholderText() == "Nom, hôte, utilisateur…"


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
    # Colonne 3 ("Dernier test") — layout uniforme à 6 colonnes sur les 6 tableaux depuis le lot
    # A-Connexions (icône/Connexion/Cible/Dernier test/Utilisée par/Actions).
    assert _cell_texts(view.ssh_table, 0, 3)[0] == expected_text


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
    assert _cell_texts(view.elevation_table, 0, 3)[0] == expected_text


def test_database_health_badge_reflects_last_test_success(qapp, test_db):
    from ui.main_window.connections_view import ConnectionsView

    p = db.create_oracle_profile(name="ORA1", host="h", port=1521, service_name="s",
                                  username="u", password="pw")
    db.record_profile_test_result("oracle", p.id, True)

    view = ConnectionsView()
    assert _cell_texts(view.database_table, 0, 3)[0] == "OK"


def test_health_badge_dims_a_profile_not_retested_recently(qapp, test_db):
    """Fraîcheur visuelle (chantier identité, vague 1, idée 11 ; refonte lot A-Connexions, A5) :
    un profil testé il y a plus de 30 jours s'estompe (effet d'opacité) et porte désormais
    « · à retester » en texte visible (plus une infobulle) ; un profil testé récemment reste
    net."""
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
    rows = {_cell_texts(view.ssh_table, r, 1)[0]: r for r in range(view.ssh_table.rowCount())}
    fresh_cell = view.ssh_table.cellWidget(rows["EDGE-FRESH"], 3)
    stale_cell = view.ssh_table.cellWidget(rows["EDGE-STALE"], 3)

    assert fresh_cell.graphicsEffect() is None
    assert stale_cell.graphicsEffect() is not None
    assert "à retester" in _cell_texts(view.ssh_table, rows["EDGE-STALE"], 3)[1]


def test_search_filters_across_active_tab_tables(qapp, test_db):
    from ui.main_window.connections_view import ConnectionsView

    db.create_ssh_profile(name="EDGE-ALPHA", host="h1", port=22, username="u", password="pw")
    db.create_ssh_profile(name="EDGE-BETA", host="h2", port=22, username="u", password="pw")

    view = ConnectionsView()
    view.inp_search.setText("alpha")

    assert not view.ssh_table.isRowHidden(0)
    assert view.ssh_table.isRowHidden(1)


def test_search_matches_the_target_column_too(qapp, test_db):
    """A1/A3 : la recherche porte sur la Cible (hôte/utilisateur), pas seulement sur le nom —
    texte du champ : "Nom, hôte, utilisateur…"."""
    from ui.main_window.connections_view import ConnectionsView

    db.create_ssh_profile(name="SERVEUR-UN", host="h1", port=22, username="svc_myspecialuser", password="pw")
    db.create_ssh_profile(name="SERVEUR-DEUX", host="h2", port=22, username="other", password="pw")

    view = ConnectionsView()
    view.inp_search.setText("myspecialuser")

    rows = {_cell_texts(view.ssh_table, r, 1)[0]: r for r in range(view.ssh_table.rowCount())}
    assert not view.ssh_table.isRowHidden(rows["SERVEUR-UN"])
    assert view.ssh_table.isRowHidden(rows["SERVEUR-DEUX"])


def test_ftp_and_smtp_tables_show_two_line_connexion_and_cible_cells(qapp, test_db):
    """A3/A7 : Connexion = nom + type ; Cible = hôte:port + utilisateur/expéditeur, icône de
    famille en colonne 0."""
    from ui.main_window.connections_view import ConnectionsView

    db.create_ftp_profile(name="Partage ventes", host="ftp.interne", port=990,
                           protocol="FTPS", username="kulu", password="pw")
    db.create_smtp_profile(name="SMTP Interne", host="smtp.interne", port=587,
                            use_tls=True, from_address="kulu@entreprise.fr")

    view = ConnectionsView()

    ftp_connexion = _cell_texts(view.ftp_table, 0, 1)
    assert ftp_connexion == ["Partage ventes", "FTPS"]
    ftp_cible = _cell_texts(view.ftp_table, 0, 2)
    assert ftp_cible == ["ftp.interne:990", "kulu"]

    smtp_connexion = _cell_texts(view.smtp_table, 0, 1)
    assert smtp_connexion == ["SMTP Interne", "SMTP · STARTTLS"]
    smtp_cible = _cell_texts(view.smtp_table, 0, 2)
    assert smtp_cible == ["smtp.interne:587", "kulu@entreprise.fr"]

    assert view.ftp_table.cellWidget(0, 0) is not None
    assert view.smtp_table.cellWidget(0, 0) is not None


def test_kerberos_and_elevation_cible_has_no_second_line(qapp, test_db):
    """A3 : Kerberos/Élévation n'ont pas d'hôte/port/utilisateur — une seule ligne de Cible."""
    from ui.main_window.connections_view import ConnectionsView

    db.create_kerberos_profile(name="KRB-SOLO", principal="svc@REALM", password="pw")
    db.create_elevation_profile(name="ELEV-SOLO", target_user="hdfs", password="pw")

    view = ConnectionsView()
    assert _cell_texts(view.kerberos_table, 0, 2) == ["svc@REALM"]
    assert _cell_texts(view.elevation_table, 0, 2) == ["sudo su hdfs"]
