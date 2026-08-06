"""
DataScheduler — tests/test_import_type_compatibility.py
Vérifie que plan_import() refuse proprement un bundle référençant un type d'étape ou une
catégorie de profil inconnus de cette version de l'application (chantier gouvernance de version,
G.3), plutôt que d'importer "avec succès" puis d'échouer confusément plus tard (à l'édition ou à
l'exécution du step/profil concerné). schema_version ne suivant que la structure du bundle (voir
sa docstring), il ne détectait pas ce cas — SPARK_SQL a d'ailleurs été ajouté au format exportable
sans bump de schema_version, exactement le scénario que ce correctif couvre.
"""

from database import db_manager as db
from database.export_import import export_pipeline, plan_import


def _make_pipeline_with_oracle_extract():
    profile = db.create_oracle_profile(
        name="ORACLE_PROD", host="10.0.0.1", port=1521,
        username="scott", password="tiger", service_name="PROD",
    )
    query = db.create_sql_query(name="VENTES", sql_text="SELECT * FROM ventes")
    pipeline = db.create_pipeline(name="compat-test", frequency="DAILY", scheduled_time="06:00")
    db.save_steps(pipeline.id, [{
        "step_type": "DB_EXTRACT",
        "label": "Extraction ventes",
        "config": {"db_type": "ORACLE", "profile_id": profile.id, "sql_query_id": query.id},
    }])
    return pipeline, profile, query


def test_unknown_step_type_is_rejected_cleanly(test_db):
    pipeline, profile, query = _make_pipeline_with_oracle_extract()
    export_result = export_pipeline(pipeline.id)
    assert export_result.success

    bundle = export_result.bundle
    # Simule un bundle exporté par une version future de l'app, avec un type d'étape que
    # celle-ci ne connaît pas encore — même schema_version, contenu différent.
    bundle["pipeline"]["steps"][0]["step_type"] = "FUTURE_STEP_TYPE"

    plan = plan_import(bundle)

    assert not plan.success
    assert "FUTURE_STEP_TYPE" in plan.error
    assert "type" in plan.error.lower()


def test_unknown_profile_category_is_rejected_cleanly(test_db):
    pipeline, profile, query = _make_pipeline_with_oracle_extract()
    export_result = export_pipeline(pipeline.id)
    assert export_result.success

    bundle = export_result.bundle
    bundle["profiles"]["future_category"] = [{"uuid": "x", "name": "y"}]

    plan = plan_import(bundle)

    assert not plan.success
    assert "future_category" in plan.error


def test_ordinary_bundle_with_only_known_types_is_accepted(test_db):
    """Non-régression : un bundle normal, qui ne référence que des types connus, doit rester
    importable sans être bloqué par le nouveau correctif."""
    pipeline, profile, query = _make_pipeline_with_oracle_extract()
    export_result = export_pipeline(pipeline.id)
    assert export_result.success

    plan = plan_import(export_result.bundle)

    assert plan.success, plan.error


def test_spark_sql_bundle_is_accepted_by_current_version(test_db):
    """SPARK_SQL est un type connu de cette version — pas de faux positif."""
    edge = db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="p")
    krb  = db.create_kerberos_profile(name="KRB1", principal="u@REALM", password="p")
    query = db.create_sql_query(name="Q1", sql_text="SELECT 1")
    pipeline = db.create_pipeline(name="spark-compat-test")
    db.save_steps(pipeline.id, [{
        "step_type": "SPARK_SQL",
        "config": {
            "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "sql_query_id": query.id,
            "fetch_result": False,
        },
    }])

    export_result = export_pipeline(pipeline.id)
    assert export_result.success

    plan = plan_import(export_result.bundle)

    assert plan.success, plan.error
