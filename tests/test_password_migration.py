"""
DataScheduler — tests/test_password_migration.py
Vérifie que _migrate() chiffre bien, une seule fois, les mots de passe encore en
clair d'une base créée avant l'introduction du chiffrement au repos.
"""

from sqlalchemy import create_engine, text

from database import crypto, db_manager as db


def test_migrate_encrypts_plaintext_passwords(tmp_path):
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")

    # Simule une vraie base pré-chiffrement (et pré-UUID) : table dans sa forme d'origine,
    # mot de passe inséré directement en clair, en contournant crypto.encrypt(). On ne
    # passe pas par Base.metadata.create_all() ici, qui reflète le schéma actuel (uuid
    # NOT NULL compris) — ce test isole spécifiquement la migration de chiffrement.
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
