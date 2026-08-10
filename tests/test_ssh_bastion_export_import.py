"""
DataScheduler — tests/test_ssh_bastion_export_import.py
Vérifie l'export/import d'un chaînage bastion SSH (chantier M) : EDGE01 (bastion) n'est jamais
référencé directement par une étape — seule EDGE03 (jump_via_id=EDGE01) l'est — donc la
découverte habituelle des profils (marche uniquement en parcourant les configs d'étapes) doit
être complétée par une clôture transitive côté export ; côté import, le câblage de jump_via_id
doit fonctionner même si EDGE03 apparaît dans le bundle avant EDGE01 (ordre non garanti — c'est
d'ailleurs l'ordre naturel produit par l'export, la découverte transitive ajoutant le bastion
après le profil qui le référence).
"""

import json

from database import crypto, db_manager as db
from database.export_import import export_pipeline, plan_import, apply_import


def _make_pipeline_with_bastion():
    edge01 = db.create_ssh_profile(name="EDGE01", host="edge01.cluster.local", port=22,
                                    username="jdupont", password="bastionsecret")
    edge03 = db.create_ssh_profile(name="EDGE03", host="edge03.cluster.local", port=22,
                                    username="jdupont", password="targetsecret",
                                    jump_via_id=edge01.id)
    elevation = db.create_elevation_profile(name="NIFI", target_user="nifi", password="sharedpw")
    pipeline = db.create_pipeline(name="bastion-export-test")
    db.save_steps(pipeline.id, [{
        "step_type": "SQOOP_EXPORT",
        "label": "Export Sqoop (via bastion)",
        "config": {
            "edge_profile_id": edge03.id, "elevation_profile_id": elevation.id,
            "oracle_profile_id": db.create_oracle_profile(
                name="ORA1", host="10.0.0.5", port=1521, username="ORAUSER",
                password="orasecret", service_name="PRODDB").id,
            "hcatalog_database": "DD", "hcatalog_table": "T", "oracle_table": "x.y",
        },
    }])
    return pipeline, edge01, edge03


def test_export_transitively_includes_the_bastion_never_referenced_by_a_step(test_db):
    pipeline, edge01, edge03 = _make_pipeline_with_bastion()
    result = export_pipeline(pipeline.id, password="exportpw")
    assert result.success, result.error

    ssh_bundle = result.bundle["profiles"]["ssh"]
    uuids = {p["uuid"] for p in ssh_bundle}
    assert edge01.uuid in uuids   # jamais référencé par l'étape, découvert via jump_via_id
    assert edge03.uuid in uuids

    by_uuid = {p["uuid"]: p for p in ssh_bundle}
    assert by_uuid[edge03.uuid]["jump_via_uuid"] == edge01.uuid
    assert by_uuid[edge01.uuid]["jump_via_uuid"] is None

    # Ordre naturel de la découverte transitive : EDGE03 (référencé par l'étape) est inséré
    # avant EDGE01 (son bastion, découvert après coup) — exactement le cas à risque pour
    # l'import si celui-ci supposait un ordre topologique.
    assert [p["uuid"] for p in ssh_bundle].index(edge03.uuid) < \
           [p["uuid"] for p in ssh_bundle].index(edge01.uuid)


def test_import_into_fresh_db_wires_jump_via_id_regardless_of_bundle_order(test_db, tmp_path):
    pipeline, edge01, edge03 = _make_pipeline_with_bastion()
    export_result = export_pipeline(pipeline.id, password="exportpw")
    assert export_result.success

    db.init_db(tmp_path / "target.db")

    plan = plan_import(export_result.bundle, password="exportpw")
    assert plan.success, plan.error
    apply_result = apply_import(plan)
    assert apply_result.success, apply_result.error

    new_edge01 = db.get_ssh_profile_by_uuid(edge01.uuid)
    new_edge03 = db.get_ssh_profile_by_uuid(edge03.uuid)
    assert new_edge01 is not None and new_edge03 is not None
    assert new_edge03.jump_via_id == new_edge01.id
    assert new_edge01.jump_via_id is None
    assert crypto.decrypt(new_edge01.password) == "bastionsecret"
    assert crypto.decrypt(new_edge03.password) == "targetsecret"


def test_import_reusing_an_existing_bastion_does_not_rewire_it(test_db, tmp_path):
    """Un profil "reuse" (déjà présent en local, matché par uuid) ne doit jamais voir son
    jump_via_id modifié par l'import — seuls les profils nouvellement créés sont câblés."""
    pipeline, edge01, edge03 = _make_pipeline_with_bastion()
    export_result = export_pipeline(pipeline.id, password="exportpw")
    assert export_result.success

    db.init_db(tmp_path / "target.db")
    # Le bastion existe déjà en local (même uuid, donc "reuse"), avec un jump_via différent.
    other_bastion = db.create_ssh_profile(name="AUTRE", host="autre", port=22, username="u",
                                           password="pw")
    db.create_ssh_profile(name="EDGE01", host="edge01.cluster.local", port=22,
                           username="jdupont", password="bastionsecret", uuid=edge01.uuid,
                           jump_via_id=other_bastion.id)

    plan = plan_import(export_result.bundle, password="exportpw")
    apply_result = apply_import(plan)
    assert apply_result.success, apply_result.error

    reused_edge01 = db.get_ssh_profile_by_uuid(edge01.uuid)
    assert reused_edge01.jump_via_id == other_bastion.id   # inchangé, pas écrasé par l'import
