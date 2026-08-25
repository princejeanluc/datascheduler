"""
DataScheduler — tests/test_export_import.py
Vérifie l'export de pipeline (chantier 5a) : forme du bundle, traduction des références de
profil en UUID, chiffrement des secrets, et dégradation propre en cas de référence manquante.
L'import n'existe pas encore (chantier 5b) — ces tests ne couvrent que l'export.
"""

import base64
import json

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import Fernet

from database import db_manager as db
from database.export_import import export_pipeline, export_pipeline_to_file, CURRENT_SCHEMA_VERSION


def _make_pipeline_with_oracle_extract(test_db):
    profile = db.create_oracle_profile(
        name="ORACLE_PROD", host="10.0.0.1", port=1521,
        username="scott", password="tiger", service_name="PROD",
    )
    query = db.create_sql_query(name="VENTES", sql_text="SELECT * FROM ventes")
    pipeline = db.create_pipeline(name="export-test", frequency="DAILY", scheduled_time="06:00")
    db.save_steps(pipeline.id, [{
        "step_type": "DB_EXTRACT",
        "label": "Extraction ventes",
        "config": {"db_type": "ORACLE", "profile_id": profile.id, "sql_query_id": query.id},
        # Valeurs non triviales délibérément (pas 0/False/0) — ce sont aussi les valeurs par
        # défaut côté lecture (step.get(clé, 0)), donc un bug de câblage qui perdrait ces champs
        # à l'export passerait inaperçu avec 0/False/0. Voir test_export_includes_execution_policy.
        "retry_count": 2,
        "run_always": True,
        "timeout_s": 600,
    }])
    return pipeline, profile, query


def _make_graph_pipeline(test_db):
    """Pipeline construit comme le ferait l'éditeur graphique (chantier 6b) : deux étapes
    positionnées sur le canevas, reliées par une arête explicite."""
    pipeline = db.create_pipeline(name="graph-export-test")
    db.save_pipeline_graph(pipeline.id, steps=[
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}, "pos_x": 60, "pos_y": 60},
        {"step_type": "LOCAL_COPY", "config": {"_step_key": "b"}, "pos_x": 300, "pos_y": 60},
    ], edges=[
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
    ])
    return pipeline


def test_export_bundle_shape(test_db):
    pipeline, profile, query = _make_pipeline_with_oracle_extract(test_db)

    result = export_pipeline(pipeline.id)

    assert result.success, result.error
    bundle = result.bundle
    assert bundle["schema_version"] == CURRENT_SCHEMA_VERSION
    assert bundle["kind"] == "pipeline"
    assert "app_version" in bundle and "exported_at" in bundle
    assert bundle["pipeline"]["uuid"] == pipeline.uuid
    assert bundle["pipeline"]["name"] == "export-test"
    assert len(bundle["pipeline"]["steps"]) == 1
    assert len(bundle["profiles"]["oracle"]) == 1
    assert bundle["profiles"]["oracle"][0]["uuid"] == profile.uuid
    assert len(bundle["sql_queries"]) == 1
    assert bundle["sql_queries"][0]["uuid"] == query.uuid


def test_export_includes_execution_policy(test_db):
    """retry_count/run_always/timeout_s sont des colonnes PipelineStep (pas du config_json) —
    vérifie qu'elles survivent bien dans le bundle exporté, avec des valeurs non triviales."""
    pipeline, profile, query = _make_pipeline_with_oracle_extract(test_db)

    result = export_pipeline(pipeline.id)

    step = result.bundle["pipeline"]["steps"][0]
    assert step["retry_count"] == 2
    assert step["run_always"] is True
    assert step["timeout_s"] == 600


def test_export_includes_is_active(test_db):
    """Correctif : is_active n'était pas du tout capturé par le bundle — un pipeline désactivé
    exporté puis réimporté se réactivait silencieusement (create_pipeline() par défaut actif,
    jamais touché par apply_import())."""
    pipeline, profile, query = _make_pipeline_with_oracle_extract(test_db)
    db.set_pipeline_active(pipeline.id, False)

    result = export_pipeline(pipeline.id)

    assert result.bundle["pipeline"]["is_active"] is False


def test_export_translates_profile_references_to_uuid(test_db):
    pipeline, profile, query = _make_pipeline_with_oracle_extract(test_db)

    result = export_pipeline(pipeline.id)

    step_config = result.bundle["pipeline"]["steps"][0]["config"]
    assert step_config["profile_uuid"] == profile.uuid
    assert step_config["sql_query_uuid"] == query.uuid
    assert "profile_id" not in step_config
    assert "sql_query_id" not in step_config
    # La base locale, elle, ne doit jamais être modifiée par l'export.
    assert json.loads(db.get_steps(pipeline.id)[0].config_json)["profile_id"] == profile.id


def test_export_with_password_encrypts_only_password_field(test_db):
    pipeline, profile, query = _make_pipeline_with_oracle_extract(test_db)

    result = export_pipeline(pipeline.id, password="correct horse battery staple")

    oracle_entry = result.bundle["profiles"]["oracle"][0]
    assert oracle_entry["password_status"] == "encrypted"
    assert oracle_entry["host"] == "10.0.0.1"          # en clair
    assert oracle_entry["username"] == "scott"          # en clair
    assert "tiger" not in json.dumps(result.bundle)     # le mot de passe en clair ne fuite nulle part

    kdf_meta = result.bundle["kdf"]
    salt = base64.b64decode(kdf_meta["salt"])
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=kdf_meta["iterations"])
    key = base64.urlsafe_b64encode(kdf.derive(b"correct horse battery staple"))
    fernet = Fernet(key)
    assert fernet.decrypt(oracle_entry["encrypted_password"].encode()).decode() == "tiger"


def test_export_without_password_omits_secrets(test_db):
    pipeline, profile, query = _make_pipeline_with_oracle_extract(test_db)

    result = export_pipeline(pipeline.id)

    oracle_entry = result.bundle["profiles"]["oracle"][0]
    assert oracle_entry["password_status"] == "omitted"
    assert "encrypted_password" not in oracle_entry
    assert "kdf" not in result.bundle


def test_export_flags_dangling_profile_reference(test_db):
    pipeline, profile, query = _make_pipeline_with_oracle_extract(test_db)
    db.delete_oracle_profile(profile.id)

    result = export_pipeline(pipeline.id)

    assert result.success
    assert len(result.warnings) == 1
    assert "introuvable" in result.warnings[0]
    step_config = result.bundle["pipeline"]["steps"][0]["config"]
    assert step_config["profile_uuid"] is None
    assert result.bundle["profiles"]["oracle"] == []


def test_export_nonexistent_pipeline_fails_cleanly(test_db):
    result = export_pipeline(999_999)
    assert not result.success
    assert result.bundle is None
    assert "introuvable" in result.error


def test_export_pipeline_to_file_writes_readable_json(test_db, tmp_path):
    pipeline, profile, query = _make_pipeline_with_oracle_extract(test_db)
    out_path = tmp_path / "export-test.dspipeline"

    result = export_pipeline_to_file(pipeline.id, out_path, password="hunter2")

    assert result.success
    assert out_path.exists()
    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    assert on_disk["pipeline"]["uuid"] == pipeline.uuid


# ──────────────────────────────────────────────
#  Export d'un pipeline en graphe (chantier 6a/6b) — arêtes + positions
# ──────────────────────────────────────────────

def test_export_includes_edges_and_positions(test_db):
    pipeline = _make_graph_pipeline(test_db)

    result = export_pipeline(pipeline.id)

    assert result.success, result.error
    steps = result.bundle["pipeline"]["steps"]
    assert {s["config"]["_step_key"]: (s["pos_x"], s["pos_y"]) for s in steps} == {
        "a": (60, 60), "b": (300, 60),
    }
    edges = result.bundle["pipeline"]["edges"]
    assert edges == [
        {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
    ]


def test_export_of_linear_pipeline_has_empty_edges(test_db):
    pipeline, _, _ = _make_pipeline_with_oracle_extract(test_db)

    result = export_pipeline(pipeline.id)

    assert result.success
    assert result.bundle["pipeline"]["edges"] == []
