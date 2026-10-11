"""
DataScheduler — tests/test_atelier_sidebar_collapse.py
Repli de la sidebar de pipelines dans l'Atelier Pipelines (chantier Atelier Pipelines, écran 2) :
état mémorisé dans AppSettings.atelier_sidebar_collapsed, même patron que
AppSettings.nav_collapsed (voir tests/test_nav_rail_collapse.py, section AppSettings). Ce fichier
ne couvre ici que le modèle/la migration (AtelierSidebar — le composant Qt — arrive dans un
commit ultérieur du même chantier ; les tests de câblage widget<->AppSettings suivront le même
patron que test_mainwindow_wires_collapsed_changed_to_app_settings une fois ce composant écrit).
"""

from database import db_manager as db


def test_new_app_settings_row_defaults_to_expanded(test_db):
    """Comportement historique préservé pour qui n'a jamais touché à ce réglage — une nouvelle
    colonne ne doit jamais changer silencieusement le comportement par défaut."""
    assert db.get_app_settings().atelier_sidebar_collapsed is False


def test_app_settings_atelier_sidebar_collapsed_round_trip(test_db):
    db.update_app_settings(atelier_sidebar_collapsed=True)
    assert db.get_app_settings().atelier_sidebar_collapsed is True
    db.update_app_settings(atelier_sidebar_collapsed=False)
    assert db.get_app_settings().atelier_sidebar_collapsed is False


def test_atelier_sidebar_collapsed_independent_from_nav_collapsed(test_db):
    """Les deux réglages de repli (nav rail, sidebar de l'Atelier) sont deux colonnes
    indépendantes — changer l'une ne doit jamais affecter l'autre."""
    db.update_app_settings(nav_collapsed=True)
    assert db.get_app_settings().atelier_sidebar_collapsed is False
    db.update_app_settings(atelier_sidebar_collapsed=True)
    assert db.get_app_settings().nav_collapsed is True
    assert db.get_app_settings().atelier_sidebar_collapsed is True
