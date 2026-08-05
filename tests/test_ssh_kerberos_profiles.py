"""
DataScheduler — tests/test_ssh_kerberos_profiles.py
Vérifie les profils SSH (edge/master node) et Kerberos (étape SPARK_SQL) : CRUD, chiffrement du
mot de passe, convention "vide en édition = conserver", identité UUID, câblage avec le bilan de
santé des connexions, et migration idempotente sur une base "legacy" (avant l'ajout de ces deux
tables) — même patron que tests/test_connection_health.py.
"""

from sqlalchemy import create_engine, text

from database import crypto, db_manager as db


# ──────────────────────────────────────────────
#  SshProfile
# ──────────────────────────────────────────────

def test_create_ssh_profile_encrypts_password(test_db):
    p = db.create_ssh_profile(name="EDGE01", host="edge01.cluster.local", port=22,
                               username="jdupont", password="secret")
    assert p.password != "secret"
    assert crypto.decrypt(p.password) == "secret"
    assert p.uuid


def test_ssh_profile_crud(test_db):
    p = db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="pw")
    assert db.get_ssh_profile(p.id).host == "edge01"
    assert len(db.get_ssh_profiles()) == 1
    assert db.get_ssh_profile_by_uuid(p.uuid).id == p.id

    db.update_ssh_profile(p.id, name="EDGE01", host="edge02", port=2222, username="u2", password=None)
    reloaded = db.get_ssh_profile(p.id)
    assert reloaded.host == "edge02" and reloaded.port == 2222 and reloaded.username == "u2"
    assert crypto.decrypt(reloaded.password) == "pw"   # mot de passe conservé (vide = inchangé)

    db.update_ssh_profile(p.id, name="EDGE01", host="edge02", port=2222, username="u2", password="new")
    assert crypto.decrypt(db.get_ssh_profile(p.id).password) == "new"

    assert db.delete_ssh_profile(p.id) is True
    assert db.get_ssh_profile(p.id) is None


def test_ssh_profile_health_board_wiring(test_db):
    p = db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="pw")
    assert p.last_tested_at is None and p.last_test_success is None

    db.record_profile_test_result("ssh", p.id, True)
    tested = db.get_ssh_profile(p.id)
    assert tested.last_test_success is True
    assert tested.last_tested_at is not None

    db.record_profile_test_result("ssh", p.id, False)
    assert db.get_ssh_profile(p.id).last_test_success is False


# ──────────────────────────────────────────────
#  KerberosProfile
# ──────────────────────────────────────────────

def test_create_kerberos_profile_encrypts_password(test_db):
    p = db.create_kerberos_profile(name="KRB_JDUPONT", principal="jdupont@REALM.EXAMPLE",
                                    password="secret")
    assert p.password != "secret"
    assert crypto.decrypt(p.password) == "secret"
    assert p.uuid


def test_kerberos_profile_crud(test_db):
    p = db.create_kerberos_profile(name="KRB1", principal="a@REALM", password="pw")
    assert db.get_kerberos_profile(p.id).principal == "a@REALM"
    assert len(db.get_kerberos_profiles()) == 1
    assert db.get_kerberos_profile_by_uuid(p.uuid).id == p.id

    db.update_kerberos_profile(p.id, name="KRB1", principal="b@REALM", password=None)
    reloaded = db.get_kerberos_profile(p.id)
    assert reloaded.principal == "b@REALM"
    assert crypto.decrypt(reloaded.password) == "pw"

    db.update_kerberos_profile(p.id, name="KRB1", principal="b@REALM", password="new")
    assert crypto.decrypt(db.get_kerberos_profile(p.id).password) == "new"

    assert db.delete_kerberos_profile(p.id) is True
    assert db.get_kerberos_profile(p.id) is None


def test_kerberos_profile_health_board_wiring(test_db):
    p = db.create_kerberos_profile(name="KRB1", principal="a@REALM", password="pw")
    db.record_profile_test_result("kerberos", p.id, True)
    assert db.get_kerberos_profile(p.id).last_test_success is True


# ──────────────────────────────────────────────
#  Schéma — ssh_profiles/kerberos_profiles sont des tables neuves, toujours créées en entier
#  par Base.metadata.create_all() (jamais de lignes existantes migrées colonne par colonne,
#  contrairement à un ALTER TABLE sur une table déjà peuplée) — on vérifie juste que init_db()
#  les crée correctement avec toutes les colonnes attendues, sur une base fraîche comme sur une
#  base pré-existante quelconque, sans planter.
# ──────────────────────────────────────────────

def test_init_db_creates_ssh_and_kerberos_tables_with_expected_columns(tmp_path):
    db_path = tmp_path / "some_pre_existing.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        # Une base pré-existante quelconque, sans rapport avec ces 2 tables — s'assure que
        # _migrate() ne suppose pas une base totalement vierge.
        conn.execute(text("CREATE TABLE unrelated_table (id INTEGER PRIMARY KEY)"))
        conn.commit()
    engine.dispose()

    db.init_db(db_path)
    cols_ssh = {r[1] for r in create_engine(f"sqlite:///{db_path}").connect()
                .execute(text("PRAGMA table_info(ssh_profiles)")).fetchall()}
    cols_krb = {r[1] for r in create_engine(f"sqlite:///{db_path}").connect()
                .execute(text("PRAGMA table_info(kerberos_profiles)")).fetchall()}
    for col in ("uuid", "name", "host", "port", "username", "password",
                "last_tested_at", "last_test_success"):
        assert col in cols_ssh
    for col in ("uuid", "name", "principal", "password", "last_tested_at", "last_test_success"):
        assert col in cols_krb

    # Idempotence : un second démarrage ne doit pas planter.
    db.init_db(db_path)
    db._engine = None
    db._SessionFactory = None
