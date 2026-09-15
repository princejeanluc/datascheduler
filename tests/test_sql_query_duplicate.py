"""
DataScheduler — tests/test_sql_query_duplicate.py
db_manager.duplicate_sql_query() (chantier atelier SQL) : clone une requête avec une identité
complètement indépendante, désambiguïsation de nom même patron que duplicate_pipeline().
"""

from database import db_manager as db


def test_duplicate_creates_an_independent_copy(test_db):
    original = db.create_sql_query(name="VENTES_JOUR", sql_text="SELECT 1", description="d",
                                    oracle_profile_id=None)
    copy = db.duplicate_sql_query(original.id)

    assert copy.id != original.id
    assert copy.uuid != original.uuid
    assert copy.name == "VENTES_JOUR (copie)"
    assert copy.sql_text == "SELECT 1"
    assert copy.description == "d"

    # Indépendance : modifier l'original ne doit jamais affecter la copie.
    with db.get_session() as s:
        from database.models import SqlQuery
        obj = s.get(SqlQuery, original.id)
        obj.sql_text = "SELECT 2"
    assert db.get_sql_query(copy.id).sql_text == "SELECT 1"


def test_duplicate_carries_over_oracle_profile(test_db):
    profile = db.create_oracle_profile(name="ORA1", host="h", port=1521, username="u",
                                        password="p", service_name="S")
    original = db.create_sql_query(name="Q", sql_text="SELECT 1", oracle_profile_id=profile.id)
    copy = db.duplicate_sql_query(original.id)
    assert copy.oracle_profile_id == profile.id


def test_duplicate_disambiguates_name_when_copy_suffix_already_taken(test_db):
    original = db.create_sql_query(name="Q", sql_text="SELECT 1")
    db.create_sql_query(name="Q (copie)", sql_text="SELECT 2")
    copy = db.duplicate_sql_query(original.id)
    assert copy.name == "Q (copie) 2"


def test_duplicate_of_unknown_id_returns_none(test_db):
    assert db.duplicate_sql_query(999999) is None
