"""
DataScheduler — tests/test_list_all_db_profiles_last_tested_at.py
Correctif K3 (docs/refonte/LOTS.md) : list_all_db_profiles() doit exposer last_tested_at (déjà
stocké sur OracleProfile/DatabaseProfile) pour que connections_view.py puisse afficher
l'ancienneté du test, exactement comme pour FTP/SMTP/SSH (_health_badge).
"""

from database import db_manager as db


def test_oracle_profile_exposes_last_tested_at(test_db):
    profile = db.create_oracle_profile(name="ORA1", host="h", port=1521, username="u", password="p")
    db.record_profile_test_result("oracle", profile.id, True)

    row = next(r for r in db.list_all_db_profiles() if r["id"] == profile.id and r["db_type"] == "ORACLE")
    assert row["last_tested_at"] is not None


def test_database_profile_exposes_last_tested_at(test_db):
    profile = db.create_database_profile(name="MYSQL1", db_type="MYSQL", host="h", port=3306,
                                          username="u", password="p")
    db.record_profile_test_result("database", profile.id, False)

    row = next(r for r in db.list_all_db_profiles() if r["id"] == profile.id and r["db_type"] == "MYSQL")
    assert row["last_tested_at"] is not None


def test_never_tested_profile_has_none_last_tested_at(test_db):
    profile = db.create_oracle_profile(name="ORA2", host="h", port=1521, username="u", password="p")

    row = next(r for r in db.list_all_db_profiles() if r["id"] == profile.id)
    assert row["last_tested_at"] is None
