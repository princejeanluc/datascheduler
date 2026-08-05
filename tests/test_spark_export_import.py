"""
DataScheduler — tests/test_spark_export_import.py
Vérifie l'export/import d'un pipeline contenant une étape SPARK_SQL (chantier Spark SQL, D.4) :
le bundle contient bien les 2 nouvelles catégories de profil (ssh/kerberos), les références sont
traduites en UUID à l'export puis retraduites en id local à l'import, mots de passe chiffrés
préservés — mêmes garanties déjà vérifiées pour DB_EXTRACT/FTP_UPLOAD/EMAIL_NOTIFY.
"""

import json

from database import crypto, db_manager as db
from database.export_import import export_pipeline, plan_import, apply_import


def _make_spark_pipeline():
    edge = db.create_ssh_profile(name="EDGE01", host="edge01.cluster.local", port=22,
                                  username="jdupont", password="sshsecret")
    krb = db.create_kerberos_profile(name="KRB1", principal="jdupont@REALM.EXAMPLE",
                                      password="krbsecret")
    query = db.create_sql_query(name="Q1", sql_text="SELECT 1")
    pipeline = db.create_pipeline(name="spark-export-test")
    db.save_steps(pipeline.id, [{
        "step_type": "SPARK_SQL",
        "label": "Requête Spark",
        "config": {
            "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "sql_query_id": query.id,
            "fetch_result": True, "output_name": "spark_result",
            "spark_conf": "--conf spark.yarn.queue=default",
        },
    }])
    return pipeline, edge, krb, query


def test_export_includes_ssh_and_kerberos_categories(test_db):
    pipeline, edge, krb, query = _make_spark_pipeline()
    result = export_pipeline(pipeline.id, password="exportpw")
    assert result.success, result.error

    bundle = result.bundle
    assert len(bundle["profiles"]["ssh"]) == 1
    assert len(bundle["profiles"]["kerberos"]) == 1
    assert bundle["profiles"]["ssh"][0]["uuid"] == edge.uuid
    assert bundle["profiles"]["kerberos"][0]["uuid"] == krb.uuid


def test_export_translates_step_references_to_uuid(test_db):
    pipeline, edge, krb, query = _make_spark_pipeline()
    result = export_pipeline(pipeline.id, password="exportpw")
    step_config = result.bundle["pipeline"]["steps"][0]["config"]

    assert step_config["edge_profile_uuid"] == edge.uuid
    assert step_config["kerberos_profile_uuid"] == krb.uuid
    assert step_config["sql_query_uuid"] == query.uuid
    # ids locaux retirés — n'ont aucun sens sur une autre machine.
    assert "edge_profile_id" not in step_config
    assert "kerberos_profile_id" not in step_config
    assert "sql_query_id" not in step_config


def test_export_encrypts_ssh_and_kerberos_passwords(test_db):
    _make_spark_pipeline()
    pipeline = db.get_pipelines()[0]
    result = export_pipeline(pipeline.id, password="exportpw")

    ssh_entry = result.bundle["profiles"]["ssh"][0]
    krb_entry = result.bundle["profiles"]["kerberos"][0]
    assert ssh_entry["password_status"] == "encrypted"
    assert krb_entry["password_status"] == "encrypted"
    assert "encrypted_password" in ssh_entry
    assert "encrypted_password" in krb_entry


def test_export_omits_passwords_without_export_password(test_db):
    _make_spark_pipeline()
    pipeline = db.get_pipelines()[0]
    result = export_pipeline(pipeline.id, password=None)

    assert result.bundle["profiles"]["ssh"][0]["password_status"] == "omitted"
    assert result.bundle["profiles"]["kerberos"][0]["password_status"] == "omitted"


def test_import_into_fresh_db_recreates_profiles_with_same_uuid_and_password(test_db, tmp_path):
    pipeline, edge, krb, query = _make_spark_pipeline()
    export_result = export_pipeline(pipeline.id, password="exportpw")
    assert export_result.success

    # Simule "autre machine" : nouvelle base, plus rien en commun.
    db.init_db(tmp_path / "target.db")

    plan = plan_import(export_result.bundle, password="exportpw")
    assert plan.success, plan.error
    apply_result = apply_import(plan)
    assert apply_result.success, apply_result.error

    new_edge = db.get_ssh_profiles()[0]
    new_krb = db.get_kerberos_profiles()[0]
    assert new_edge.uuid == edge.uuid
    assert new_krb.uuid == krb.uuid
    assert crypto.decrypt(new_edge.password) == "sshsecret"
    assert crypto.decrypt(new_krb.password) == "krbsecret"

    steps = db.get_steps(apply_result.pipeline_id)
    config = json.loads(steps[0].config_json)
    assert config["edge_profile_id"] == new_edge.id
    assert config["kerberos_profile_id"] == new_krb.id
    assert config["output_name"] == "spark_result"


def test_reimport_into_same_db_reuses_existing_profiles(test_db, tmp_path):
    """Réimport du même bundle dans la base où les profils existent déjà (par UUID) — ne doit
    jamais dupliquer les profils SSH/Kerberos, même règle déjà garantie pour les autres profils."""
    pipeline, edge, krb, query = _make_spark_pipeline()
    export_result = export_pipeline(pipeline.id, password="exportpw")

    plan = plan_import(export_result.bundle, password="exportpw")
    apply_result = apply_import(plan)
    assert apply_result.success, apply_result.error

    assert len(db.get_ssh_profiles()) == 1     # pas de doublon
    assert len(db.get_kerberos_profiles()) == 1

    steps = db.get_steps(apply_result.pipeline_id)
    config = json.loads(steps[0].config_json)
    assert config["edge_profile_id"] == edge.id       # réutilise le profil existant
    assert config["kerberos_profile_id"] == krb.id
