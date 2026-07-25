"""
DataScheduler — tests/test_password_migration.py
Vérifie que _migrate() chiffre bien, une seule fois, les mots de passe encore en
clair d'une base créée avant l'introduction du chiffrement au repos.
"""

from sqlalchemy import create_engine, text

from database import crypto, db_manager as db
from database.models import Base


def test_migrate_encrypts_plaintext_passwords(tmp_path):
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    # Simule une base pré-chiffrement : mot de passe inséré directement en clair,
    # en contournant crypto.encrypt().
    with engine.connect() as conn:
        conn.execute(text(
            "INSERT INTO oracle_profiles (name, host, port, username, password, auth_mode) "
            "VALUES ('LEGACY', 'h', 1521, 'u', 'plain_secret', 'DEFAULT')"
        ))
        conn.commit()
    engine.dispose()

    # init_db() déclenche _migrate(), qui doit détecter et chiffrer ce mot de passe.
    db.init_db(db_path)
    profile = db.get_oracle_profiles()[0]
    assert profile.password != "plain_secret"
    assert crypto.decrypt(profile.password) == "plain_secret"

    # Idempotence : un second démarrage ne doit pas re-chiffrer un mot de passe déjà migré.
    db.init_db(db_path)
    profile_again = db.get_oracle_profiles()[0]
    assert profile_again.password == profile.password

    db._engine = None
    db._SessionFactory = None
