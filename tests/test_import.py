"""
DataScheduler — tests/test_import.py
Vérifie l'import de pipeline (chantier 5b core, sans écran de revue) : réutilisation par
UUID, collision de pipeline (toujours une copie renommée, jamais un écrasement),
désambiguïsation de nom, mot de passe, version de schéma, et fidélité du ciblage de
contexte (chantier 3, _step_key/reads_from_step_key) après un aller-retour export/import.
"""

import json

from database import db_manager as db
from database.export_import import export_pipeline, plan_import, apply_import, CURRENT_SCHEMA_VERSION


def _make_pipeline_with_oracle_extract():
    profile = db.create_oracle_profile(
        name="ORACLE_PROD", host="10.0.0.1", port=1521,
        username="scott", password="tiger", service_name="PROD",
    )
    query = db.create_sql_query(name="VENTES", sql_text="SELECT * FROM ventes")
    pipeline = db.create_pipeline(name="import-test", frequency="DAILY", scheduled_time="06:00")
    db.save_steps(pipeline.id, [{
        "step_type": "DB_EXTRACT",
        "label": "Extraction ventes",
        "config": {"db_type": "ORACLE", "profile_id": profile.id, "sql_query_id": query.id},
        "retry_count": 0,
        "run_always": False,
    }])
    return pipeline, profile, query


def test_reimport_same_bundle_into_same_db_reuses_profiles_and_renames_pipeline(test_db):
    pipeline, profile, query = _make_pipeline_with_oracle_extract()
    export_result = export_pipeline(pipeline.id)
    assert export_result.success

    plan = plan_import(export_result.bundle)
    assert plan.success
    assert plan.pipeline_action == "collision"
    assert all(d.action == "reuse" for d in plan.profile_decisions)
    assert all(d.action == "reuse" for d in plan.sql_query_decisions)

    result = apply_import(plan)
    assert result.success, result.error

    pipelines = db.get_pipelines()
    names = {p.name for p in pipelines}
    assert "import-test" in names
    assert "import-test (import)" in names
    assert len(db.get_oracle_profiles()) == 1   # pas dupliqué
    assert len(db.get_sql_queries()) == 1        # pas dupliquée

    new_pipeline = next(p for p in pipelines if p.name == "import-test (import)")
    assert new_pipeline.uuid != pipeline.uuid
    new_steps = db.get_steps(new_pipeline.id)
    assert len(new_steps) == 1
    new_config = json.loads(new_steps[0].config_json)
    assert new_config["profile_id"] == profile.id   # rebranché vers le profil réutilisé
    assert new_config["sql_query_id"] == query.id


def test_import_same_bundle_into_fresh_db_recreates_with_original_uuids(tmp_path):
    db.init_db(tmp_path / "a.db")
    pipeline, profile, query = _make_pipeline_with_oracle_extract()
    export_result = export_pipeline(pipeline.id)
    assert export_result.success
    bundle = export_result.bundle
    pipeline_uuid, profile_uuid = pipeline.uuid, profile.uuid
    db._engine = None
    db._SessionFactory = None

    db.init_db(tmp_path / "b.db")
    try:
        plan = plan_import(bundle)
        assert plan.success
        assert plan.pipeline_action == "create"
        assert all(d.action == "create" for d in plan.profile_decisions)

        result = apply_import(plan)
        assert result.success, result.error

        imported_pipeline = db.get_pipeline_by_uuid(pipeline_uuid)
        assert imported_pipeline is not None
        assert imported_pipeline.name == "import-test"

        imported_profile = db.get_oracle_profile_by_uuid(profile_uuid)
        assert imported_profile is not None
        assert imported_profile.name == "ORACLE_PROD"
    finally:
        db._engine = None
        db._SessionFactory = None


def test_wrong_password_fails_cleanly(test_db):
    pipeline, profile, query = _make_pipeline_with_oracle_extract()
    export_result = export_pipeline(pipeline.id, password="correct password")

    plan = plan_import(export_result.bundle, password="wrong password")

    assert not plan.success
    assert "incorrect" in plan.error.lower()


def test_encrypted_bundle_without_password_needs_password(test_db):
    pipeline, profile, query = _make_pipeline_with_oracle_extract()
    export_result = export_pipeline(pipeline.id, password="secret")

    plan = plan_import(export_result.bundle)

    assert not plan.success
    assert plan.needs_password


def test_schema_version_too_new_is_rejected(test_db):
    pipeline, profile, query = _make_pipeline_with_oracle_extract()
    export_result = export_pipeline(pipeline.id)
    bundle = export_result.bundle
    bundle["schema_version"] = CURRENT_SCHEMA_VERSION + 1

    plan = plan_import(bundle)

    assert not plan.success
    assert "récente" in plan.error


def test_name_collision_with_unrelated_local_profile_is_disambiguated(tmp_path):
    db.init_db(tmp_path / "a.db")
    pipeline, profile, query = _make_pipeline_with_oracle_extract()
    export_result = export_pipeline(pipeline.id)
    bundle = export_result.bundle
    db._engine = None
    db._SessionFactory = None

    db.init_db(tmp_path / "b.db")
    try:
        unrelated = db.create_oracle_profile(
            name="ORACLE_PROD", host="unrelated-host", port=1521,
            username="other", password="whatever", service_name="OTHER",
        )

        plan = plan_import(bundle)
        result = apply_import(plan)

        assert result.success, result.error
        names = {p.name for p in db.get_oracle_profiles()}
        assert "ORACLE_PROD" in names
        assert "ORACLE_PROD (2)" in names
        untouched = db.get_oracle_profile(unrelated.id)
        assert untouched.host == "unrelated-host"   # le profil local existant n'est pas touché
    finally:
        db._engine = None
        db._SessionFactory = None


def test_step_targeting_preserved_across_export_import(tmp_path):
    """
    _step_key/reads_from_step_key (chantier 3) voyagent tels quels dans le bundle — après
    import, une étape qui ciblait explicitement une autre étape productrice du même pipeline
    doit toujours pointer vers elle (même valeur de clé partagée entre les deux étapes).
    """
    db.init_db(tmp_path / "a.db")
    pipeline_uuid = None
    try:
        pipeline = db.create_pipeline(name="targeting-test")
        db.save_steps(pipeline.id, [
            {"step_type": "DB_EXTRACT", "config": {"_step_key": "prod1"}},
            {"step_type": "DB_EXTRACT", "config": {"_step_key": "prod2"}},
            {"step_type": "LOCAL_COPY", "config": {"reads_from_step_key": "prod1"}},
        ])
        export_result = export_pipeline(pipeline.id)
        assert export_result.success
        bundle = export_result.bundle
    finally:
        db._engine = None
        db._SessionFactory = None

    db.init_db(tmp_path / "b.db")
    try:
        plan = plan_import(bundle)
        result = apply_import(plan)
        assert result.success, result.error

        steps = db.get_steps(result.pipeline_id)
        configs = [json.loads(s.config_json) for s in steps]
        producer_keys = [c["_step_key"] for c in configs if c.get("_step_key")]
        assert len(set(producer_keys)) == 2   # les deux DB_EXTRACT gardent des clés distinctes

        consumer_config = next(c for c in configs if "reads_from_step_key" in c)
        first_producer_config = configs[0]
        assert consumer_config["reads_from_step_key"] == first_producer_config["_step_key"]
    finally:
        db._engine = None
        db._SessionFactory = None
