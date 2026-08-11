"""
DataScheduler — tests/test_db_manager.py
Vérifie que les modèles et le CRUD de database/db_manager.py fonctionnent correctement.
"""

from database import crypto, db_manager as db


def test_oracle_profile(test_db):
    db.create_oracle_profile(
        name="ORACLE_PROD", host="10.10.1.15", port=1521,
        username="reporting", password="secret",
        service_name="PROD",
    )
    profiles = db.get_oracle_profiles()
    assert len(profiles) == 1
    assert profiles[0].name == "ORACLE_PROD"
    # Le mot de passe ne doit jamais être stocké en clair.
    assert profiles[0].password != "secret"
    assert crypto.decrypt(profiles[0].password) == "secret"


def test_oracle_profile_update_keeps_password_when_blank(test_db):
    created = db.create_oracle_profile(
        name="ORACLE_PROD", host="h1", port=1521,
        username="u", password="original_secret", service_name="PROD",
    )
    db.update_oracle_profile(
        created.id, name="ORACLE_PROD", host="h2", port=1521,
        username="u", password=None, service_name="PROD",
    )
    updated = db.get_oracle_profile(created.id)
    assert updated.host == "h2"
    assert crypto.decrypt(updated.password) == "original_secret"

    db.update_oracle_profile(
        created.id, name="ORACLE_PROD", host="h2", port=1521,
        username="u", password="new_secret", service_name="PROD",
    )
    updated = db.get_oracle_profile(created.id)
    assert crypto.decrypt(updated.password) == "new_secret"


def test_ftp_profile(test_db):
    db.create_ftp_profile(
        name="FTP_FINANCE", host="ftp.company.com", port=21,
        username="ftpuser", password="ftppass", protocol="FTPS",
    )
    profiles = db.get_ftp_profiles()
    assert len(profiles) == 1
    assert profiles[0].protocol == "FTPS"


def test_sql_query(test_db):
    oracle_id = db.create_oracle_profile(
        name="ORACLE_PROD", host="h", port=1521,
        username="u", password="p", service_name="PROD",
    ).id

    db.create_sql_query(
        name="REQUETE_VENTES_JOUR",
        sql_text="SELECT * FROM sales WHERE sale_date >= TRUNC(SYSDATE)-1",
        description="Ventes de la veille",
        oracle_profile_id=oracle_id,
    )
    queries = db.get_sql_queries()
    assert len(queries) == 1


def test_pipeline(test_db):
    oracle_id = db.create_oracle_profile(
        name="ORACLE_PROD", host="h", port=1521,
        username="u", password="p", service_name="PROD",
    ).id
    ftp_id = db.create_ftp_profile(
        name="FTP_FINANCE", host="ftp.company.com", port=21,
        username="ftpuser", password="ftppass", protocol="FTPS",
    ).id
    query_id = db.create_sql_query(
        name="REQUETE_VENTES_JOUR",
        sql_text="SELECT * FROM sales",
        oracle_profile_id=oracle_id,
    ).id

    db.create_pipeline(
        name="EXPORT_VENTES_QUOTIDIEN",
        oracle_profile_id=oracle_id,
        sql_query_id=query_id,
        ftp_profile_id=ftp_id,
        remote_path_tpl="/export/finance/{yyyy}/{MM}/",
        filename_tpl="ventes_{yyyyMMdd}.csv",
        frequency="DAILY",
        scheduled_time="06:00",
    )
    pipelines = db.get_pipelines()
    assert len(pipelines) == 1
    assert pipelines[0].filename_tpl == "ventes_{yyyyMMdd}.csv"


def test_update_pipeline(test_db):
    created = db.create_pipeline(name="ORIGINAL", scheduled_time="06:00")

    updated = db.update_pipeline(
        created.id, name="RENAMED", description="nouvelle description",
        frequency="WEEKLY", scheduled_time="08:00", scheduled_day=2,
    )
    assert updated is not None
    reloaded = db.get_pipeline(created.id)
    assert reloaded.name == "RENAMED"
    assert reloaded.description == "nouvelle description"
    assert reloaded.scheduled_time == "08:00"
    assert reloaded.uuid == created.uuid   # l'UUID ne bouge jamais sur une mise à jour

    assert db.update_pipeline(999_999, name="X") is None


def test_run(test_db):
    pipeline_id = db.create_pipeline(name="EXPORT_VENTES_QUOTIDIEN").id

    run = db.create_run(pipeline_id)
    assert run.id is not None

    ok = db.finish_run(
        run.id,
        status="SUCCESS",
        rows_exported=2_435_612,
        remote_path="/export/finance/2026/06/ventes_20260608.csv",
        log_text="Connexion OK\nRequête OK\nExport OK\nUpload OK",
    )
    assert ok

    runs = db.get_runs(pipeline_id)
    assert len(runs) == 1
    assert runs[0].rows_exported == 2_435_612
    assert runs[0].duration_seconds is not None


# ──────────────────────────────────────────────
#  VISIBILITÉ DES RUNS EN COURS (chantier N)
# ──────────────────────────────────────────────

def test_update_run_progress_updates_step_and_log_without_touching_status(test_db):
    pipeline_id = db.create_pipeline(name="P1").id
    run = db.create_run(pipeline_id)

    db.update_run_progress(run.id, "Étape 1/3 : Export", "[10:00:00] Pipeline démarré")

    reloaded = db.get_run(run.id)
    assert reloaded.current_step_label == "Étape 1/3 : Export"
    assert reloaded.log_text == "[10:00:00] Pipeline démarré"
    assert reloaded.status == "RUNNING"   # inchangé — update_run_progress n'écrit pas status
    assert reloaded.finished_at is None


def test_finish_run_clears_current_step_label(test_db):
    pipeline_id = db.create_pipeline(name="P1").id
    run = db.create_run(pipeline_id)
    db.update_run_progress(run.id, "Étape 2/2 : Envoi", "log partiel")

    db.finish_run(run.id, status="SUCCESS", log_text="log complet")

    reloaded = db.get_run(run.id)
    assert reloaded.current_step_label is None
    assert reloaded.log_text == "log complet"


def test_get_running_step_labels_returns_most_recent_run_per_pipeline(test_db):
    p1 = db.create_pipeline(name="P1").id
    p2 = db.create_pipeline(name="P2").id

    older = db.create_run(p1)
    db.update_run_progress(older.id, "Étape 1/2 (ancien run)", "…")
    db.finish_run(older.id, status="FAILED")   # terminé — ne doit plus apparaître

    newer = db.create_run(p1)
    db.update_run_progress(newer.id, "Étape 1/2 (run courant)", "…")

    run2 = db.create_run(p2)
    # Jamais de update_run_progress pour p2 — current_step_label reste NULL.

    labels = db.get_running_step_labels()
    assert labels[p1] == "Étape 1/2 (run courant)"
    assert labels[p2] == "Étape en cours…"   # valeur par défaut quand le label est encore vide


def test_reconcile_stale_runs_marks_stuck_running_runs_as_failed(test_db):
    from database.models import Pipeline

    p = db.create_pipeline(name="P1")
    run = db.create_run(p.id)   # jamais finish_run() — simule un crash de l'app en plein run
    db.update_run_progress(run.id, "Étape 2/5 : Export", "log partiel")
    with db.get_session() as s:
        s.get(Pipeline, p.id).last_status = "RUNNING"

    n = db.reconcile_stale_runs()
    assert n == 1

    reloaded_run = db.get_run(run.id)
    assert reloaded_run.status == "FAILED"
    assert reloaded_run.finished_at is not None
    assert "redémarrage" in reloaded_run.error_message
    assert reloaded_run.current_step_label is None

    with db.get_session() as s:
        assert s.get(Pipeline, p.id).last_status == "FAILED"


def test_reconcile_stale_runs_leaves_finished_runs_and_other_pipelines_untouched(test_db):
    from database.models import Pipeline

    p_ok = db.create_pipeline(name="P_OK")
    run_ok = db.create_run(p_ok.id)
    db.finish_run(run_ok.id, status="SUCCESS")
    with db.get_session() as s:
        s.get(Pipeline, p_ok.id).last_status = "SUCCESS"

    assert db.reconcile_stale_runs() == 0
    assert db.get_run(run_ok.id).status == "SUCCESS"
    with db.get_session() as s:
        assert s.get(Pipeline, p_ok.id).last_status == "SUCCESS"


def test_migrate_adds_current_step_label_to_a_pre_existing_pipeline_runs_table(tmp_path):
    """Table pipeline_runs "legacy" (antérieure au chantier N) — exerce réellement le bloc
    ALTER TABLE ajouté à _migrate(), pas seulement Base.metadata.create_all() sur une base
    neuve qui créerait la colonne d'office."""
    from sqlalchemy import create_engine, text

    db_path = tmp_path / "legacy_runs.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        # pipelines n'est volontairement PAS pré-créée : Base.metadata.create_all() (appelé par
        # init_db() avant _migrate()) la créera dans sa forme moderne complète, seule
        # pipeline_runs doit être "legacy" pour exercer réellement le bloc ALTER TABLE.
        conn.execute(text(
            "CREATE TABLE pipeline_runs (id INTEGER PRIMARY KEY, pipeline_id INTEGER, "
            "started_at DATETIME, finished_at DATETIME, status VARCHAR(20), "
            "rows_exported INTEGER, remote_path VARCHAR(500), error_message TEXT, log_text TEXT)"
        ))
        conn.commit()
    engine.dispose()

    db.init_db(db_path)
    cols = {r[1] for r in create_engine(f"sqlite:///{db_path}").connect()
            .execute(text("PRAGMA table_info(pipeline_runs)")).fetchall()}
    assert "current_step_label" in cols

    db._engine = None
    db._SessionFactory = None


# ──────────────────────────────────────────────
#  GRAPHE DE PIPELINE (chantier 6a)
# ──────────────────────────────────────────────

def test_save_pipeline_graph_persists_steps_positions_and_edges(test_db):
    pipeline = db.create_pipeline(name="GRAPH_TEST")

    db.save_pipeline_graph(
        pipeline.id,
        steps=[
            {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}, "pos_x": 10, "pos_y": 20},
            {"step_type": "DB_LOAD", "config": {"_step_key": "b"}},   # pas de position -> défaut 0
        ],
        edges=[{"from_step_key": "a", "from_port": "output_file", "to_step_key": "b", "to_port": "input"}],
    )

    steps = db.get_steps(pipeline.id)
    assert len(steps) == 2
    assert steps[0].pos_x == 10 and steps[0].pos_y == 20
    assert steps[1].pos_x == 0 and steps[1].pos_y == 0

    edges = db.get_edges(pipeline.id)
    assert len(edges) == 1
    assert edges[0].from_step_key == "a"
    assert edges[0].to_step_key == "b"
    assert edges[0].from_port == "output_file"


def test_save_pipeline_graph_replaces_edges_entirely_on_resave(test_db):
    pipeline = db.create_pipeline(name="GRAPH_RESAVE")
    steps = [
        {"step_type": "DB_EXTRACT", "config": {"_step_key": "a"}},
        {"step_type": "DB_LOAD", "config": {"_step_key": "b"}},
    ]
    db.save_pipeline_graph(pipeline.id, steps, edges=[
        {"from_step_key": "a", "to_step_key": "b"},
    ])
    assert len(db.get_edges(pipeline.id)) == 1

    db.save_pipeline_graph(pipeline.id, steps, edges=[])
    assert db.get_edges(pipeline.id) == []


def test_get_edges_empty_for_pipeline_never_saved_as_graph(test_db):
    pipeline = db.create_pipeline(name="LINEAR_ONLY")
    db.save_steps(pipeline.id, [
        {"step_type": "DB_EXTRACT", "config": {}},
    ])
    assert db.get_edges(pipeline.id) == []


def test_migrate_backfills_pos_columns_on_legacy_db(tmp_path):
    from sqlalchemy import create_engine, text
    from database.models import Base

    db_path = tmp_path / "legacy_pos.db"
    engine = create_engine(f"sqlite:///{db_path}")

    # Schéma actuel pour toutes les tables (pipelines, pipeline_edges, etc.), sauf
    # pipeline_steps qu'on remplace ensuite par sa forme antérieure à ce chantier (sans
    # pos_x/pos_y) — init_db() ne recrée pas une table déjà existante (CREATE TABLE IF NOT
    # EXISTS), c'est _migrate() qui doit combler l'écart, comme lors d'une vraie mise à jour.
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE pipeline_steps"))
        conn.execute(text("""
            CREATE TABLE pipeline_steps (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                pipeline_id INTEGER NOT NULL,
                step_order  INTEGER NOT NULL,
                step_type   VARCHAR(14) NOT NULL,
                label       VARCHAR(100),
                config_json TEXT NOT NULL,
                retry_count INTEGER NOT NULL DEFAULT 0,
                run_always  BOOLEAN NOT NULL DEFAULT 0
            )
        """))
        conn.execute(text(
            "INSERT INTO pipelines (uuid, name, csv_separator, csv_encoding, csv_chunk_size, "
            "csv_quoting, frequency, is_active, prevent_overlap) "
            "VALUES ('11111111-1111-1111-1111-111111111111', 'LEGACY', ';', 'utf-8', 50000, "
            "'QUOTE_NONNUMERIC', 'DAILY', 1, 0)"
        ))
        conn.execute(text(
            "INSERT INTO pipeline_steps (pipeline_id, step_order, step_type, config_json) "
            "VALUES (1, 0, 'DB_EXTRACT', '{}')"
        ))
        conn.commit()
    engine.dispose()

    db.init_db(db_path)
    steps = db.get_steps(1)
    assert len(steps) == 1
    assert steps[0].pos_x == 0
    assert steps[0].pos_y == 0

    # Idempotence : relancer init_db() une seconde fois ne casse rien.
    db.init_db(db_path)
    assert len(db.get_steps(1)) == 1

    db._engine = None
    db._SessionFactory = None
