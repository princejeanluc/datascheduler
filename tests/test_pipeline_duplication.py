"""
DataScheduler — tests/test_pipeline_duplication.py
Vérifie database.export_import.duplicate_pipeline() (chantier UX autonomie, C.1) : réutilise la
chaîne export→import in-process — profils/requêtes réutilisés (jamais dupliqués), nom
désambiguïsé "(copie)", copie désactivée par défaut, journal d'audit cohérent.
"""

import json

from database import db_manager as db
from database.export_import import duplicate_pipeline


def test_duplicate_reuses_profiles_and_disables_copy(test_db):
    profile = db.create_oracle_profile(
        name="ORA1", host="h", port=1521, username="u", password="p", service_name="SVC",
    )
    query = db.create_sql_query(name="Q1", sql_text="SELECT 1 FROM DUAL")
    p = db.create_pipeline(name="pipeline-source", frequency="DAILY", scheduled_time="07:00")
    db.save_steps(p.id, [{
        "step_type": "DB_EXTRACT",
        "config": {"db_type": "ORACLE", "profile_id": profile.id, "sql_query_id": query.id},
    }])
    db.set_pipeline_active(p.id, True)

    result = duplicate_pipeline(p.id)
    assert result.success, result.error

    dup = db.get_pipeline(result.pipeline_id)
    assert dup.name == "pipeline-source (copie)"
    assert dup.is_active is False
    assert dup.scheduled_time == "07:00"

    steps = db.get_steps(dup.id)
    cfg = json.loads(steps[0].config_json)
    assert cfg["profile_id"] == profile.id
    assert cfg["sql_query_id"] == query.id

    # Un seul profil/une seule requête en base — pas de doublon créé.
    assert len(db.get_oracle_profiles()) == 1
    assert len(db.get_sql_queries()) == 1


def test_duplicate_disambiguates_name_on_repeat(test_db):
    p = db.create_pipeline(name="pipeline-repeat")
    db.save_steps(p.id, [{"step_type": "DB_EXTRACT", "config": {}}])

    first = duplicate_pipeline(p.id)
    second = duplicate_pipeline(p.id)
    assert first.success and second.success

    name1 = db.get_pipeline(first.pipeline_id).name
    name2 = db.get_pipeline(second.pipeline_id).name
    assert name1 != name2
    assert name1 == "pipeline-repeat (copie)"


def test_duplicate_logs_audit_event(test_db):
    p = db.create_pipeline(name="pipeline-audit")
    db.save_steps(p.id, [{"step_type": "DB_EXTRACT", "config": {}}])

    result = duplicate_pipeline(p.id)
    assert result.success

    events = db.get_audit_events(pipeline_id=result.pipeline_id)
    assert events[0].event_type == "pipeline_duplicated"
    assert "pipeline-audit" in events[0].detail


def test_duplicate_missing_pipeline_fails_cleanly(test_db):
    result = duplicate_pipeline(999)
    assert not result.success
    assert result.error
