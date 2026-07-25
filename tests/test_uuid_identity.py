"""
DataScheduler — tests/test_uuid_identity.py
Vérifie l'identité stable (UUID) sur les entités nommées/réutilisables : génération
automatique à la création, migration d'une base legacy sans colonne uuid, et unicité
réellement appliquée au niveau base (pas seulement cosmétique).
"""

import sqlite3

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from database import db_manager as db
from database.models import Base


def test_create_functions_populate_distinct_uuids(test_db):
    p1 = db.create_oracle_profile(name="A", host="h", port=1521,
                                   username="u", password="p", service_name="S")
    p2 = db.create_oracle_profile(name="B", host="h", port=1521,
                                   username="u", password="p", service_name="S")
    assert p1.uuid
    assert p2.uuid
    assert p1.uuid != p2.uuid

    ftp = db.create_ftp_profile(name="FTP", host="h", port=21, username="u", password="p")
    smtp = db.create_smtp_profile(name="SMTP", host="h", port=587, from_address="a@b.c")
    dbp = db.create_database_profile(name="DBP", db_type="MYSQL", host="h", port=3306,
                                      username="u", password="p")
    query = db.create_sql_query(name="Q", sql_text="SELECT 1")
    pipeline = db.create_pipeline(name="P")

    for obj in (ftp, smtp, dbp, query, pipeline):
        assert obj.uuid


def test_migrate_backfills_uuid_on_legacy_db(tmp_path):
    db_path = tmp_path / "legacy_uuid.db"
    engine = create_engine(f"sqlite:///{db_path}")

    # Simule une base antérieure à ce chantier : la table oracle_profiles existe déjà,
    # dans sa forme d'avant (pas de colonne uuid). init_db() ne la recrée pas
    # (Base.metadata.create_all utilise CREATE TABLE IF NOT EXISTS) — c'est _migrate()
    # qui doit détecter et combler l'écart, comme lors d'une vraie mise à jour.
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE oracle_profiles (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         VARCHAR(100) NOT NULL UNIQUE,
                host         VARCHAR(255) NOT NULL,
                port         INTEGER NOT NULL DEFAULT 1521,
                service_name VARCHAR(100),
                sid          VARCHAR(100),
                username     VARCHAR(100) NOT NULL,
                password     VARCHAR(255) NOT NULL,
                auth_mode    VARCHAR(20) NOT NULL DEFAULT 'DEFAULT',
                created_at   DATETIME,
                updated_at   DATETIME
            )
        """))
        conn.execute(text(
            "INSERT INTO oracle_profiles (name, host, port, username, password, auth_mode) "
            "VALUES ('LEGACY', 'h', 1521, 'u', 'p', 'DEFAULT')"
        ))
        conn.commit()
    engine.dispose()

    db.init_db(db_path)
    profile = db.get_oracle_profiles()[0]
    assert profile.uuid is not None and len(profile.uuid) == 36

    # Idempotence : un second démarrage ne doit pas changer l'UUID déjà attribué.
    db.init_db(db_path)
    assert db.get_oracle_profiles()[0].uuid == profile.uuid

    db._engine = None
    db._SessionFactory = None


def test_uuid_uniqueness_is_enforced_at_db_level(test_db):
    p = db.create_oracle_profile(name="A", host="h", port=1521,
                                  username="u", password="p", service_name="S")

    with pytest.raises(IntegrityError):
        with db.get_session() as s:
            from database.models import OracleProfile
            dup = OracleProfile(
                name="B", host="h", port=1521, username="u", password="p",
                service_name="S", uuid=p.uuid,
            )
            s.add(dup)
