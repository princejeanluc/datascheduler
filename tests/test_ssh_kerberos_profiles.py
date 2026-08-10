"""
DataScheduler — tests/test_ssh_kerberos_profiles.py
Vérifie les profils SSH (edge/master node), Kerberos (étape SPARK_SQL) et Élévation — sudo su
(étape SQOOP_EXPORT, chantier L) : CRUD, chiffrement du mot de passe, convention "vide en
édition = conserver", identité UUID, câblage avec le bilan de santé des connexions, et migration
idempotente sur une base "legacy" (avant l'ajout de ces tables) — même patron que
tests/test_connection_health.py.
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
#  SshProfile.jump_via_id — chaînage bastion (chantier M)
# ──────────────────────────────────────────────

def test_ssh_profile_jump_via_crud(test_db):
    edge01 = db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="pw")
    edge03 = db.create_ssh_profile(name="EDGE03", host="edge03", port=22, username="u", password="pw",
                                    jump_via_id=edge01.id)
    assert db.get_ssh_profile(edge03.id).jump_via_id == edge01.id

    db.update_ssh_profile(edge03.id, name="EDGE03", host="edge03", port=22, username="u",
                           jump_via_id=None)
    assert db.get_ssh_profile(edge03.id).jump_via_id is None

    db.update_ssh_profile(edge03.id, name="EDGE03", host="edge03", port=22, username="u",
                           jump_via_id=edge01.id)
    assert db.get_ssh_profile(edge03.id).jump_via_id == edge01.id


def test_ssh_profile_jump_via_rejects_self_reference(test_db):
    edge01 = db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="pw")
    try:
        db.update_ssh_profile(edge01.id, name="EDGE01", host="edge01", port=22, username="u",
                               jump_via_id=edge01.id)
        assert False, "devait lever ValueError (boucle A->A)"
    except ValueError as e:
        assert "boucle" in str(e)


def test_ssh_profile_jump_via_rejects_two_hop_cycle(test_db):
    edge01 = db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="pw")
    edge03 = db.create_ssh_profile(name="EDGE03", host="edge03", port=22, username="u", password="pw",
                                    jump_via_id=edge01.id)
    try:
        db.update_ssh_profile(edge01.id, name="EDGE01", host="edge01", port=22, username="u",
                               jump_via_id=edge03.id)
        assert False, "devait lever ValueError (boucle EDGE01->EDGE03->EDGE01)"
    except ValueError as e:
        assert "boucle" in str(e)
    # La tentative rejetée ne doit pas avoir modifié EDGE01 en base.
    assert db.get_ssh_profile(edge01.id).jump_via_id is None


def test_delete_ssh_profile_used_as_bastion_clears_dependents(test_db):
    edge01 = db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="pw")
    edge03 = db.create_ssh_profile(name="EDGE03", host="edge03", port=22, username="u", password="pw",
                                    jump_via_id=edge01.id)
    assert db.find_ssh_profiles_using_as_bastion(edge01.id) == ["EDGE03"]

    db.delete_ssh_profile(edge01.id)
    assert db.get_ssh_profile(edge03.id).jump_via_id is None


def test_set_ssh_profile_jump_via(test_db):
    """Setter minimal utilisé par l'import (database/export_import.py) — ne touche que cette
    colonne, ne redemande pas host/port/etc. comme le ferait update_ssh_profile."""
    edge01 = db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="pw")
    edge03 = db.create_ssh_profile(name="EDGE03", host="edge03", port=22, username="u", password="pw")

    db.set_ssh_profile_jump_via(edge03.id, edge01.id)
    reloaded = db.get_ssh_profile(edge03.id)
    assert reloaded.jump_via_id == edge01.id
    assert reloaded.host == "edge03"   # champs non touchés


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
#  ElevationProfile (sudo su — étape SQOOP_EXPORT, chantier L)
# ──────────────────────────────────────────────

def test_create_elevation_profile_encrypts_password(test_db):
    p = db.create_elevation_profile(name="NIFI", target_user="nifi", password="secret")
    assert p.password != "secret"
    assert crypto.decrypt(p.password) == "secret"
    assert p.uuid


def test_elevation_profile_crud(test_db):
    p = db.create_elevation_profile(name="NIFI", target_user="nifi", password="pw")
    assert db.get_elevation_profile(p.id).target_user == "nifi"
    assert len(db.get_elevation_profiles()) == 1
    assert db.get_elevation_profile_by_uuid(p.uuid).id == p.id

    db.update_elevation_profile(p.id, name="NIFI", target_user="nifi2", password=None)
    reloaded = db.get_elevation_profile(p.id)
    assert reloaded.target_user == "nifi2"
    assert crypto.decrypt(reloaded.password) == "pw"   # mot de passe conservé (vide = inchangé)

    db.update_elevation_profile(p.id, name="NIFI", target_user="nifi2", password="new")
    assert crypto.decrypt(db.get_elevation_profile(p.id).password) == "new"

    assert db.delete_elevation_profile(p.id) is True
    assert db.get_elevation_profile(p.id) is None


def test_elevation_profile_health_board_wiring(test_db):
    p = db.create_elevation_profile(name="NIFI", target_user="nifi", password="pw")
    assert p.last_tested_at is None and p.last_test_success is None

    db.record_profile_test_result("elevation", p.id, True)
    tested = db.get_elevation_profile(p.id)
    assert tested.last_test_success is True
    assert tested.last_tested_at is not None

    db.record_profile_test_result("elevation", p.id, False)
    assert db.get_elevation_profile(p.id).last_test_success is False


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
    cols_elevation = {r[1] for r in create_engine(f"sqlite:///{db_path}").connect()
                .execute(text("PRAGMA table_info(elevation_profiles)")).fetchall()}
    for col in ("uuid", "name", "host", "port", "username", "password", "jump_via_id",
                "last_tested_at", "last_test_success"):
        assert col in cols_ssh
    for col in ("uuid", "name", "principal", "password", "last_tested_at", "last_test_success"):
        assert col in cols_krb
    for col in ("uuid", "name", "target_user", "password", "last_tested_at", "last_test_success"):
        assert col in cols_elevation

    # Idempotence : un second démarrage ne doit pas planter.
    db.init_db(db_path)
    db._engine = None
    db._SessionFactory = None


def test_migrate_adds_jump_via_id_to_a_pre_existing_ssh_profiles_table(tmp_path):
    """Contrairement au test ci-dessus (table neuve, créée avec toutes ses colonnes d'un coup
    par Base.metadata.create_all()), ce test crée une vraie table ssh_profiles "legacy" —
    antérieure au chantier M — pour exercer réellement le bloc ALTER TABLE ajouté à _migrate()."""
    db_path = tmp_path / "legacy_ssh.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE ssh_profiles (id INTEGER PRIMARY KEY, uuid VARCHAR(36), "
            "name VARCHAR(100), host VARCHAR(255), port INTEGER, username VARCHAR(100), "
            "password VARCHAR(255))"
        ))
        conn.commit()
    engine.dispose()

    db.init_db(db_path)
    cols = {r[1] for r in create_engine(f"sqlite:///{db_path}").connect()
            .execute(text("PRAGMA table_info(ssh_profiles)")).fetchall()}
    assert "jump_via_id" in cols

    db._engine = None
    db._SessionFactory = None
