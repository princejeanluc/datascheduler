"""
DataScheduler — tests/test_sqoop_export_export_import.py
Vérifie l'export/import d'un pipeline contenant une étape SQOOP_EXPORT (chantier K) : les 3
références (ssh/kerberos/oracle) sont traduites en UUID à l'export puis retraduites en id local
à l'import, mots de passe chiffrés préservés — mêmes garanties déjà vérifiées pour SPARK_SQL
(tests/test_spark_export_import.py), dont ce fichier suit le patron. La référence Oracle réutilise
le mécanisme générique "db_profile" (db_type absent de la config, défaut ORACLE) plutôt qu'un
resolveur dédié — ce test verrouille que ce choix fonctionne bien de bout en bout.
"""

import json

from database import crypto, db_manager as db
from database.export_import import export_pipeline, plan_import, apply_import


def _make_sqoop_pipeline():
    edge = db.create_ssh_profile(name="EDGE03", host="edge03.cluster.local", port=22,
                                  username="jdupont", password="sshsecret")
    krb = db.create_kerberos_profile(name="KRB1", principal="jdupont@REALM.EXAMPLE",
                                      password="krbsecret")
    oracle = db.create_oracle_profile(name="ORA1", host="10.0.0.5", port=1521,
                                       username="ORAUSER", password="orasecret",
                                       service_name="PRODDB")
    pipeline = db.create_pipeline(name="sqoop-export-test")
    db.save_steps(pipeline.id, [{
        "step_type": "SQOOP_EXPORT",
        "label": "Export Sqoop",
        "config": {
            "edge_profile_id": edge.id, "kerberos_profile_id": krb.id,
            "oracle_profile_id": oracle.id,
            "hcatalog_database": "DD", "hcatalog_table": "FINAL_EQUIPEMENT_CLIENT",
            "oracle_table": "xxx.xxxxx",
        },
        # Valeurs non triviales délibérément (pas 0/False) — retry_count=0/run_always=False
        # "survivraient" même avec un bug de câblage (valeurs par défaut des deux côtés),
        # ce qui ne prouverait rien. timeout_s vient du chantier J.1, mergé après la conception
        # initiale de SQOOP_EXPORT — ce test verrouille qu'il fait bien partie du bundle exporté.
        "retry_count": 3, "run_always": True, "timeout_s": 900,
    }])
    return pipeline, edge, krb, oracle


def test_export_translates_all_three_references_to_uuid(test_db):
    pipeline, edge, krb, oracle = _make_sqoop_pipeline()
    result = export_pipeline(pipeline.id, password="exportpw")
    assert result.success, result.error

    step_config = result.bundle["pipeline"]["steps"][0]["config"]
    assert step_config["edge_profile_uuid"] == edge.uuid
    assert step_config["kerberos_profile_uuid"] == krb.uuid
    assert step_config["oracle_profile_uuid"] == oracle.uuid
    # ids locaux retirés — n'ont aucun sens sur une autre machine.
    assert "edge_profile_id" not in step_config
    assert "kerberos_profile_id" not in step_config
    assert "oracle_profile_id" not in step_config


def test_export_puts_oracle_profile_in_oracle_category_despite_no_db_type_field(test_db):
    """La config SQOOP_EXPORT n'a jamais de champ db_type (étape scopée Oracle uniquement) —
    vérifie que _resolve_reference()/_category_for_ref() retombent bien sur ORACLE par défaut,
    et que le profil atterrit dans bundle["profiles"]["oracle"], pas "database"."""
    pipeline, edge, krb, oracle = _make_sqoop_pipeline()
    result = export_pipeline(pipeline.id, password="exportpw")

    assert len(result.bundle["profiles"]["oracle"]) == 1
    assert result.bundle["profiles"]["oracle"][0]["uuid"] == oracle.uuid
    assert result.bundle["profiles"].get("database", []) == []


def test_import_into_fresh_db_recreates_all_three_profiles(test_db, tmp_path):
    pipeline, edge, krb, oracle = _make_sqoop_pipeline()
    export_result = export_pipeline(pipeline.id, password="exportpw")
    assert export_result.success

    db.init_db(tmp_path / "target.db")

    plan = plan_import(export_result.bundle, password="exportpw")
    assert plan.success, plan.error
    apply_result = apply_import(plan)
    assert apply_result.success, apply_result.error

    new_edge   = db.get_ssh_profiles()[0]
    new_krb    = db.get_kerberos_profiles()[0]
    new_oracle = db.get_oracle_profiles()[0]
    assert new_edge.uuid == edge.uuid
    assert new_krb.uuid == krb.uuid
    assert new_oracle.uuid == oracle.uuid
    assert crypto.decrypt(new_edge.password) == "sshsecret"
    assert crypto.decrypt(new_krb.password) == "krbsecret"
    assert crypto.decrypt(new_oracle.password) == "orasecret"

    steps = db.get_steps(apply_result.pipeline_id)
    step = steps[0]
    config = json.loads(step.config_json)
    assert config["edge_profile_id"] == new_edge.id
    assert config["kerberos_profile_id"] == new_krb.id
    assert config["oracle_profile_id"] == new_oracle.id
    assert config["hcatalog_table"] == "FINAL_EQUIPEMENT_CLIENT"
    # Politique d'exécution (retry_count/run_always/timeout_s) — des colonnes PipelineStep, pas
    # du config_json, mais tout aussi essentielles à préserver dans le bundle.
    assert step.retry_count == 3
    assert step.run_always is True
    assert step.timeout_s == 900


# ──────────────────────────────────────────────
#  Chantier L — profil d'élévation (sudo su), Kerberos désormais optionnel
# ──────────────────────────────────────────────

def _make_sqoop_pipeline_with_elevation_no_kerberos():
    """Combinaison désormais valide (chantier L) : élévation configurée, Kerberos absent —
    l'équipe qui a signalé ce besoin ne fait jamais de kinit pour Sqoop."""
    edge = db.create_ssh_profile(name="EDGE03", host="edge03.cluster.local", port=22,
                                  username="jdupont", password="sshsecret")
    elevation = db.create_elevation_profile(name="NIFI", target_user="nifi",
                                             password="sharedpw")
    oracle = db.create_oracle_profile(name="ORA1", host="10.0.0.5", port=1521,
                                       username="ORAUSER", password="orasecret",
                                       service_name="PRODDB")
    pipeline = db.create_pipeline(name="sqoop-elevation-test")
    db.save_steps(pipeline.id, [{
        "step_type": "SQOOP_EXPORT",
        "label": "Export Sqoop (élévation)",
        "config": {
            "edge_profile_id": edge.id, "elevation_profile_id": elevation.id,
            "oracle_profile_id": oracle.id,
            "hcatalog_database": "DD", "hcatalog_table": "FINAL_EQUIPEMENT_CLIENT",
            "oracle_table": "xxx.xxxxx",
        },
    }])
    return pipeline, edge, elevation, oracle


def test_export_translates_elevation_reference_and_omits_absent_kerberos(test_db):
    pipeline, edge, elevation, oracle = _make_sqoop_pipeline_with_elevation_no_kerberos()
    result = export_pipeline(pipeline.id, password="exportpw")
    assert result.success, result.error

    step_config = result.bundle["pipeline"]["steps"][0]["config"]
    assert step_config["elevation_profile_uuid"] == elevation.uuid
    # kerberos_profile_id était absent de la config — jamais résolu, jamais dans le bundle.
    assert "kerberos_profile_uuid" not in step_config
    assert "kerberos_profile_id" not in step_config
    assert len(result.bundle["profiles"]["elevation"]) == 1
    assert result.bundle["profiles"]["elevation"][0]["uuid"] == elevation.uuid


def test_import_into_fresh_db_recreates_elevation_profile_with_no_kerberos(test_db, tmp_path):
    pipeline, edge, elevation, oracle = _make_sqoop_pipeline_with_elevation_no_kerberos()
    export_result = export_pipeline(pipeline.id, password="exportpw")
    assert export_result.success

    db.init_db(tmp_path / "target.db")

    plan = plan_import(export_result.bundle, password="exportpw")
    assert plan.success, plan.error
    apply_result = apply_import(plan)
    assert apply_result.success, apply_result.error

    new_elevation = db.get_elevation_profiles()[0]
    assert new_elevation.uuid == elevation.uuid
    assert new_elevation.target_user == "nifi"
    assert crypto.decrypt(new_elevation.password) == "sharedpw"
    assert len(db.get_kerberos_profiles()) == 0   # jamais référencé, jamais créé

    steps = db.get_steps(apply_result.pipeline_id)
    config = json.loads(steps[0].config_json)
    assert config["elevation_profile_id"] == new_elevation.id
    assert "kerberos_profile_id" not in config
