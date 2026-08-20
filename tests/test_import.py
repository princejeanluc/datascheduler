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
        # Valeurs non triviales délibérément (pas 0/False/0) — ce sont aussi les valeurs par
        # défaut côté lecture, donc un bug de câblage qui perdrait ces champs à l'import
        # passerait inaperçu avec 0/False/0. Voir test_import_preserves_execution_policy.
        "retry_count": 2,
        "run_always": True,
        "timeout_s": 600,
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


def test_import_preserves_execution_policy_on_fresh_db(tmp_path):
    """retry_count/run_always/timeout_s (colonnes PipelineStep, pas du config_json) doivent
    survivre à un aller-retour export/import sur une base neuve — avec des valeurs non
    triviales, sinon un bug de câblage passerait inaperçu (0/False/0 sont aussi les défauts)."""
    db.init_db(tmp_path / "a.db")
    pipeline, profile, query = _make_pipeline_with_oracle_extract()
    export_result = export_pipeline(pipeline.id)
    assert export_result.success
    bundle = export_result.bundle
    db._engine = None
    db._SessionFactory = None

    db.init_db(tmp_path / "b.db")
    try:
        plan = plan_import(bundle)
        result = apply_import(plan)
        assert result.success, result.error

        step = db.get_steps(result.pipeline_id)[0]
        assert step.retry_count == 2
        assert step.run_always is True
        assert step.timeout_s == 600
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


def test_apply_import_with_overwrite_updates_existing_pipeline_in_place(test_db):
    pipeline, profile, query = _make_pipeline_with_oracle_extract()
    export_result = export_pipeline(pipeline.id)
    plan = plan_import(export_result.bundle)
    assert plan.pipeline_action == "collision"

    plan.pipeline_action = "overwrite"   # ce que fait PipelineImportReviewDialog._on_confirm()
    result = apply_import(plan)

    assert result.success, result.error
    assert result.pipeline_id == pipeline.id   # même id, pas de copie

    pipelines = db.get_pipelines()
    names = {p.name for p in pipelines}
    assert names == {"import-test"}   # aucune copie "(import)" créée
    reloaded = db.get_pipeline(pipeline.id)
    assert reloaded.uuid == pipeline.uuid   # UUID inchangé


def test_apply_import_with_manual_remap_reuses_chosen_profile(tmp_path):
    db.init_db(tmp_path / "a.db")
    pipeline, profile, query = _make_pipeline_with_oracle_extract()
    export_result = export_pipeline(pipeline.id)
    bundle = export_result.bundle
    db._engine = None
    db._SessionFactory = None

    db.init_db(tmp_path / "b.db")
    try:
        other_profile = db.create_oracle_profile(
            name="AUTRE_PROFIL", host="other-host", port=1521,
            username="x", password="y", service_name="OTHER",
        )

        plan = plan_import(bundle)
        oracle_decision = next(d for d in plan.profile_decisions if d.category == "oracle")
        assert oracle_decision.action == "create"

        # Ce que fait PipelineImportReviewDialog._on_confirm() quand on choisit "Remapper vers".
        oracle_decision.action = "reuse"
        oracle_decision.existing_id = other_profile.id

        result = apply_import(plan)
        assert result.success, result.error

        assert len(db.get_oracle_profiles()) == 1   # aucun nouveau profil créé
        imported_pipeline = db.get_pipeline(result.pipeline_id)
        steps = db.get_steps(imported_pipeline.id)
        config = json.loads(steps[0].config_json)
        assert config["profile_id"] == other_profile.id
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


# ──────────────────────────────────────────────
#  Export/import d'un pipeline en graphe (chantier 6a/6b) — les arêtes et positions doivent
#  survivre à l'aller-retour, sur la même base et sur une base neuve.
# ──────────────────────────────────────────────

def test_graph_pipeline_edges_and_positions_preserved_on_fresh_db(tmp_path):
    db.init_db(tmp_path / "a.db")
    try:
        pipeline = db.create_pipeline(name="graph-roundtrip")
        db.save_pipeline_graph(pipeline.id, steps=[
            {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}, "pos_x": 60, "pos_y": 60},
            {"step_type": "CONDITION",
             "config": {"_step_key": "b", "expression": "rows_count > 0"}, "pos_x": 300, "pos_y": 60},
            {"step_type": "LOCAL_COPY", "config": {"_step_key": "c"}, "pos_x": 540, "pos_y": 20},
            {"step_type": "FTP_UPLOAD", "config": {"_step_key": "d"}, "pos_x": 540, "pos_y": 120},
        ], edges=[
            {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
            {"from_step_key": "b", "from_port": "true",  "to_step_key": "c", "to_port": "input"},
            {"from_step_key": "b", "from_port": "false", "to_step_key": "d", "to_port": "input"},
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

        imported_edges = db.get_edges(result.pipeline_id)
        assert len(imported_edges) == 3
        assert {(e.from_step_key, e.from_port, e.to_step_key) for e in imported_edges} == {
            ("a", "output_file", "b"), ("b", "true", "c"), ("b", "false", "d"),
        }

        imported_steps = {
            json.loads(s.config_json)["_step_key"]: (s.pos_x, s.pos_y)
            for s in db.get_steps(result.pipeline_id)
        }
        assert imported_steps == {"a": (60, 60), "b": (300, 60), "c": (540, 20), "d": (540, 120)}
    finally:
        db._engine = None
        db._SessionFactory = None


def test_graph_pipeline_reexecutes_via_dag_path_after_reimport(tmp_path, monkeypatch):
    """Le vrai risque de régression identifié : un pipeline en graphe réimporté doit toujours
    emprunter _execute_graph (via db.get_edges), pas basculer silencieusement sur
    _execute_linear qui ignorerait le nœud CONDITION."""
    import core.steps as steps_module
    from core.steps.base import BaseStep, StepResult
    from core.pipeline import run_pipeline
    from pathlib import Path

    class _FakeProducer(BaseStep):
        PRODUCES = {"output_file"}

        def run(self, ctx, cancel_event=None, on_progress=None):
            path = Path(self.config["path"])
            path.write_text("DATA")
            ctx.output_file = path
            return StepResult(success=True)

    class _FakeSink(BaseStep):
        REQUIRES = {"output_file"}

        def run(self, ctx, cancel_event=None, on_progress=None):
            Path(self.config["sink_path"]).write_text("ran")
            return StepResult(success=True)

    monkeypatch.setitem(steps_module._REGISTRY, "DB_EXTRACT", _FakeProducer)
    monkeypatch.setitem(steps_module._REGISTRY, "LOCAL_COPY", _FakeSink)
    monkeypatch.setitem(steps_module._REGISTRY, "FTP_UPLOAD", _FakeSink)

    db.init_db(tmp_path / "a.db")
    try:
        src = tmp_path / "src.txt"
        true_sink = tmp_path / "true.txt"
        false_sink = tmp_path / "false.txt"

        pipeline = db.create_pipeline(name="graph-condition-roundtrip")
        db.save_pipeline_graph(pipeline.id, steps=[
            {"step_type": "DB_EXTRACT", "config": {"path": str(src), "_step_key": "a"}},
            {"step_type": "CONDITION",
             "config": {"_step_key": "b", "expression": "rows_count > 0"}},
            {"step_type": "LOCAL_COPY", "config": {"sink_path": str(true_sink), "_step_key": "c"}},
            {"step_type": "FTP_UPLOAD", "config": {"sink_path": str(false_sink), "_step_key": "d"}},
        ], edges=[
            {"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"},
            {"from_step_key": "b", "from_port": "true",  "to_step_key": "c", "to_port": "input"},
            {"from_step_key": "b", "from_port": "false", "to_step_key": "d", "to_port": "input"},
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

        run_result = run_pipeline(result.pipeline_id)

        assert run_result.success, run_result.error
        assert not true_sink.exists()    # rows_count > 0 est faux : branche "false" seule active
        assert false_sink.exists()
    finally:
        db._engine = None
        db._SessionFactory = None


def test_v1_style_bundle_without_edges_key_still_imports(tmp_path):
    """Un bundle fabriqué sans la clé "edges" (forme v1, avant ce correctif) doit toujours
    s'importer proprement — pipeline sans arêtes, comportement linéaire historique."""
    db.init_db(tmp_path / "only.db")
    try:
        pipeline = db.create_pipeline(name="v1-style")
        db.save_steps(pipeline.id, [
            {"step_type": "DB_EXTRACT", "config": {}},
        ])
        export_result = export_pipeline(pipeline.id)
        assert export_result.success
        bundle = export_result.bundle
        bundle["schema_version"] = 1
        del bundle["pipeline"]["edges"]
        for step in bundle["pipeline"]["steps"]:
            del step["pos_x"]
            del step["pos_y"]

        plan = plan_import(bundle)
        result = apply_import(plan)
        assert result.success, result.error
        assert db.get_edges(result.pipeline_id) == []
        assert db.get_steps(result.pipeline_id)[0].pos_x == 0
    finally:
        db._engine = None
        db._SessionFactory = None
