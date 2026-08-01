"""
DataScheduler — tests/test_audit_log.py
Vérifie le journal d'audit (chantier UX post-personas, item 3 couche 2 — persona "Nadia") :
log_audit_event/get_audit_events eux-mêmes, puis chacun des 7 points d'appel existants
(create_pipeline, update_pipeline, delete_pipeline, save_steps, save_pipeline_graph,
export_pipeline_to_file, apply_import) — vérifie qu'une opération réelle produit bien
une ligne AuditEvent avec le event_type/pipeline_name/detail attendus, pas seulement que
log_audit_event fonctionne isolément.
"""

import json

from database.export_import import apply_import, export_pipeline_to_file, plan_import


def _event_types(events):
    return [e.event_type for e in events]


# ──────────────────────────────────────────────
#  log_audit_event / get_audit_events, isolément
# ──────────────────────────────────────────────

def test_log_audit_event_captures_actor(test_db):
    event = test_db.log_audit_event("pipeline_created", pipeline_id=1, pipeline_name="p1", detail="3 étapes")
    assert event.actor  # getpass.getuser() sur la machine de test, jamais vide en CI/local
    assert event.event_type == "pipeline_created"
    assert event.pipeline_id == 1
    assert event.pipeline_name == "p1"
    assert event.detail == "3 étapes"


def test_get_audit_events_orders_most_recent_first(test_db):
    test_db.log_audit_event("pipeline_created", pipeline_id=1, pipeline_name="p1")
    test_db.log_audit_event("pipeline_edited", pipeline_id=1, pipeline_name="p1")
    events = test_db.get_audit_events()
    assert _event_types(events)[:2] == ["pipeline_edited", "pipeline_created"]


def test_get_audit_events_filters_by_pipeline_id(test_db):
    test_db.log_audit_event("pipeline_created", pipeline_id=1, pipeline_name="p1")
    test_db.log_audit_event("pipeline_created", pipeline_id=2, pipeline_name="p2")
    events = test_db.get_audit_events(pipeline_id=2)
    assert len(events) == 1
    assert events[0].pipeline_name == "p2"


def test_get_audit_events_survives_pipeline_deletion(test_db):
    """pipeline_id n'a délibérément aucune contrainte FK — un événement doit rester
    consultable même si le pipeline auquel il fait référence a depuis été supprimé."""
    p = test_db.create_pipeline(name="ephemere")
    test_db.delete_pipeline(p.id)
    events = test_db.get_audit_events(pipeline_id=p.id)
    assert any(e.event_type == "pipeline_deleted" for e in events)


# ──────────────────────────────────────────────
#  Les 7 points d'appel — chacun produit bien l'événement attendu
# ──────────────────────────────────────────────

def test_create_pipeline_logs_event(test_db):
    p = test_db.create_pipeline(name="p-create")
    events = test_db.get_audit_events(pipeline_id=p.id)
    assert _event_types(events) == ["pipeline_created"]
    assert events[0].pipeline_name == "p-create"


def test_update_pipeline_logs_event(test_db):
    p = test_db.create_pipeline(name="p-update")
    test_db.update_pipeline(p.id, name="p-update-renomme")
    events = test_db.get_audit_events(pipeline_id=p.id)
    assert "pipeline_edited" in _event_types(events)


def test_delete_pipeline_logs_event_with_name_snapshot(test_db):
    p = test_db.create_pipeline(name="p-delete")
    test_db.delete_pipeline(p.id)
    events = test_db.get_audit_events(pipeline_id=p.id)
    assert events[0].event_type == "pipeline_deleted"
    assert events[0].pipeline_name == "p-delete"


def test_save_steps_logs_event(test_db):
    p = test_db.create_pipeline(name="p-save-steps")
    test_db.save_steps(p.id, [{"step_type": "DB_EXTRACT", "config": {}}])
    events = test_db.get_audit_events(pipeline_id=p.id)
    assert events[0].event_type == "pipeline_edited"
    assert "1 étape" in events[0].detail


def test_save_pipeline_graph_logs_event(test_db):
    p = test_db.create_pipeline(name="p-save-graph")
    test_db.save_pipeline_graph(p.id, [{"step_type": "DB_EXTRACT", "config": {"_step_key": "k1"}}], [])
    events = test_db.get_audit_events(pipeline_id=p.id)
    assert events[0].event_type == "pipeline_edited"
    assert "éditeur graphique" in events[0].detail


def test_export_pipeline_to_file_logs_event(test_db, tmp_path):
    p = test_db.create_pipeline(name="p-export")
    test_db.save_steps(p.id, [{"step_type": "DB_EXTRACT", "config": {}}])
    out = tmp_path / "export.dspipeline"
    result = export_pipeline_to_file(p.id, out)
    assert result.success, result.error

    events = test_db.get_audit_events(pipeline_id=p.id)
    assert events[0].event_type == "pipeline_exported"
    assert str(out) in events[0].detail


def test_apply_import_logs_event(test_db, tmp_path):
    p = test_db.create_pipeline(name="p-import-source")
    test_db.save_steps(p.id, [{"step_type": "DB_EXTRACT", "config": {}}])
    out = tmp_path / "export.dspipeline"
    export_result = export_pipeline_to_file(p.id, out)
    assert export_result.success, export_result.error

    bundle = json.loads(out.read_text(encoding="utf-8"))
    plan = plan_import(bundle)
    apply_result = apply_import(plan)
    assert apply_result.success, apply_result.error

    events = test_db.get_audit_events(pipeline_id=apply_result.pipeline_id)
    assert events[0].event_type == "pipeline_imported"
    # apply_import appelle aussi create_pipeline/save_steps en interne : additif, pas exclusif.
    assert "pipeline_created" in _event_types(events)
