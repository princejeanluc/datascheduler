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


# ──────────────────────────────────────────────
#  DÉCLENCHEMENT CONDITIONNEL ENTRE PIPELINES (chantier P)
# ──────────────────────────────────────────────

def test_set_pipeline_trigger_assigns_updates_and_clears(test_db):
    a = db.create_pipeline(name="A")
    b = db.create_pipeline(name="B")

    db.set_pipeline_trigger(b.id, a.id, "SUCCESS")
    reloaded = db.get_pipeline(b.id)
    assert reloaded.trigger_after_pipeline_id == a.id
    assert reloaded.trigger_condition == "SUCCESS"

    db.set_pipeline_trigger(b.id, a.id, "FAILURE")
    assert db.get_pipeline(b.id).trigger_condition == "FAILURE"

    db.set_pipeline_trigger(b.id, None, None)
    reloaded = db.get_pipeline(b.id)
    assert reloaded.trigger_after_pipeline_id is None
    assert reloaded.trigger_condition is None


def test_set_pipeline_trigger_rejects_direct_and_indirect_cycles(test_db):
    a = db.create_pipeline(name="A")
    b = db.create_pipeline(name="B")

    try:
        db.set_pipeline_trigger(a.id, a.id, "SUCCESS")
        assert False, "devait lever ValueError (boucle A->A)"
    except ValueError as e:
        assert "boucle" in str(e)

    db.set_pipeline_trigger(b.id, a.id, "SUCCESS")   # B après A — valide
    try:
        db.set_pipeline_trigger(a.id, b.id, "SUCCESS")
        assert False, "devait lever ValueError (boucle A->B->A)"
    except ValueError as e:
        assert "boucle" in str(e)
    # La tentative rejetée ne doit pas avoir modifié A en base.
    assert db.get_pipeline(a.id).trigger_after_pipeline_id is None


def test_get_pipelines_triggered_by(test_db):
    a = db.create_pipeline(name="A")
    b = db.create_pipeline(name="B")
    c = db.create_pipeline(name="C")
    db.set_pipeline_trigger(b.id, a.id, "SUCCESS")
    db.set_pipeline_trigger(c.id, a.id, "FAILURE")

    children = {p.name for p in db.get_pipelines_triggered_by(a.id)}
    assert children == {"B", "C"}
    assert db.get_pipelines_triggered_by(b.id) == []


def test_delete_pipeline_clears_dependents_trigger(test_db):
    a = db.create_pipeline(name="A")
    b = db.create_pipeline(name="B")
    db.set_pipeline_trigger(b.id, a.id, "ALWAYS")

    db.delete_pipeline(a.id)
    reloaded = db.get_pipeline(b.id)
    assert reloaded.trigger_after_pipeline_id is None
    assert reloaded.trigger_condition is None


def test_migrate_adds_trigger_condition_to_a_pre_existing_pipelines_table(tmp_path):
    """Table pipelines "legacy" (antérieure au chantier P) — exerce réellement le bloc
    ALTER TABLE ajouté à _migrate(). pipelines a trop de colonnes pour être reconstruite à la
    main sans risquer un mismatch avec _migrate_legacy_pipelines() (qui fait s.query(Pipeline)
    .all(), donc échoue si une seule colonne du modèle manque) : on part d'un schéma moderne
    complet (via un premier init_db()), puis on retire trigger_condition (SQLite >= 3.35 supporte
    DROP COLUMN) pour simuler une base pré-chantier-P fidèle. trigger_after_pipeline_id n'est pas
    retirée de la même façon : c'est une auto-référence (FOREIGN KEY) que SQLite refuse de DROP
    ("column is part of a foreign key definition", même avec legacy_alter_table) — son propre
    bloc ALTER TABLE ADD COLUMN, textuellement adjacent et structurellement identique dans
    _migrate(), est donc couvert par le même mécanisme prouvé ici plutôt que testé isolément."""
    from sqlalchemy import create_engine, text

    db_path = tmp_path / "legacy_pipelines.db"
    db.init_db(db_path)
    db._engine = None
    db._SessionFactory = None

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE pipelines DROP COLUMN trigger_condition"))
        conn.commit()
    engine.dispose()

    db.init_db(db_path)
    cols = {r[1] for r in create_engine(f"sqlite:///{db_path}").connect()
            .execute(text("PRAGMA table_info(pipelines)")).fetchall()}
    assert "trigger_condition" in cols
    assert "trigger_after_pipeline_id" in cols   # jamais perdue au passage

    db._engine = None
    db._SessionFactory = None


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


def test_update_run_progress_sets_current_step_key(test_db):
    pipeline_id = db.create_pipeline(name="P1").id
    run = db.create_run(pipeline_id)

    db.update_run_progress(run.id, "Étape 1/3 : Export", "…", current_step_key="step-a")

    reloaded = db.get_run(run.id)
    assert reloaded.current_step_key == "step-a"


def test_update_run_progress_leaves_current_step_key_unchanged_when_omitted(test_db):
    """Les tickets "reprise"/"ignorée" (core/pipeline.py) n'appellent pas progress() avec un
    step_key — la dernière étape réellement en cours doit rester surlignée jusqu'au prochain
    ticket qui en fournit un nouveau, pas être effacée entre deux appels."""
    pipeline_id = db.create_pipeline(name="P1").id
    run = db.create_run(pipeline_id)

    db.update_run_progress(run.id, "Étape 1/3 : Export", "…", current_step_key="step-a")
    db.update_run_progress(run.id, "Étape 1/3 : Export (50%)", "…")   # pas de step_key

    reloaded = db.get_run(run.id)
    assert reloaded.current_step_key == "step-a"


def test_finish_run_clears_current_step_key(test_db):
    pipeline_id = db.create_pipeline(name="P1").id
    run = db.create_run(pipeline_id)
    db.update_run_progress(run.id, "Étape 2/2 : Envoi", "log partiel", current_step_key="step-b")

    db.finish_run(run.id, status="SUCCESS", log_text="log complet")

    reloaded = db.get_run(run.id)
    assert reloaded.current_step_key is None


def test_get_running_step_keys_returns_most_recent_run_per_pipeline(test_db):
    p1 = db.create_pipeline(name="P1").id
    p2 = db.create_pipeline(name="P2").id

    older = db.create_run(p1)
    db.update_run_progress(older.id, "…", "…", current_step_key="old-key")
    db.finish_run(older.id, status="FAILED")   # terminé — ne doit plus apparaître

    newer = db.create_run(p1)
    db.update_run_progress(newer.id, "…", "…", current_step_key="new-key")

    db.create_run(p2)   # jamais de step_key pour p2 — absent du résultat

    keys = db.get_running_step_keys()
    assert keys[p1] == "new-key"
    assert p2 not in keys


def test_get_runs_for_pipeline_on_day_filters_by_date_and_pipeline(test_db):
    """Calendrier de fréquence (chantier identité, vague 4, idée 13) : cliquer une case doit
    isoler les runs de CE jour pour CE pipeline, sans ramener les autres jours ni les runs d'un
    autre pipeline."""
    from datetime import date, datetime, timedelta

    p1 = db.create_pipeline(name="P1").id
    p2 = db.create_pipeline(name="P2").id
    today = date.today()
    yesterday = today - timedelta(days=1)

    run_today = db.create_run(p1)
    db.finish_run(run_today.id, status="SUCCESS")

    run_yesterday = db.create_run(p1)
    with db.get_session() as s:
        from database.models import PipelineRun
        s.get(PipelineRun, run_yesterday.id).started_at = datetime.combine(
            yesterday, datetime.min.time())
    db.finish_run(run_yesterday.id, status="FAILED")

    other_pipeline_run = db.create_run(p2)
    db.finish_run(other_pipeline_run.id, status="SUCCESS")

    runs = db.get_runs_for_pipeline_on_day(p1, today)
    assert [r.id for r in runs] == [run_today.id]


def test_migrate_adds_current_step_key_to_a_pre_existing_pipeline_runs_table(tmp_path):
    """Même patron que le test current_step_label ci-dessus — exerce réellement le bloc
    ALTER TABLE ajouté à _migrate() pour current_step_key."""
    from sqlalchemy import create_engine, text

    db_path = tmp_path / "legacy_runs_key.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
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
    assert "current_step_key" in cols

    db._engine = None
    db._SessionFactory = None


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


def test_migrate_adds_active_steps_json_to_a_pre_existing_pipeline_runs_table(tmp_path):
    """Chantier parallélisme intra-pipeline — même patron que current_step_label/
    current_step_key ci-dessus, pour la colonne active_steps_json."""
    from sqlalchemy import create_engine, text

    db_path = tmp_path / "legacy_runs_active_steps.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
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
    assert "active_steps_json" in cols

    db._engine = None
    db._SessionFactory = None


def test_migrate_adds_failed_step_key_to_a_pre_existing_pipeline_runs_table(tmp_path):
    """Chantier UX éditeur, Lot 1 (B1) — même patron que active_steps_json ci-dessus, pour la
    colonne failed_step_key."""
    from sqlalchemy import create_engine, text

    db_path = tmp_path / "legacy_runs_failed_step_key.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
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
    assert "failed_step_key" in cols

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
            "csv_quoting, frequency, is_active, prevent_overlap, parallel_execution_enabled, "
            "max_parallel_branches) "
            "VALUES ('11111111-1111-1111-1111-111111111111', 'LEGACY', ';', 'utf-8', 50000, "
            "'QUOTE_NONNUMERIC', 'DAILY', 1, 0, 0, 4)"
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


# ──────────────────────────────────────────────
#  PARAMÈTRES APPLICATIFS (chantier écran "Paramètres")
# ──────────────────────────────────────────────

def test_get_app_settings_creates_singleton_row_with_defaults(test_db):
    settings = db.get_app_settings()
    assert settings.timezone == "UTC"
    assert settings.misfire_grace_time_min == 60
    assert settings.coalesce_missed_runs is True   # préserve le comportement câblé en dur avant
    assert settings.max_concurrent_runs == 6
    assert settings.log_level == "INFO"
    assert settings.dashboard_refresh_s == 30


def test_get_app_settings_is_idempotent_get_or_create(test_db):
    first = db.get_app_settings()
    second = db.get_app_settings()
    assert first.id == second.id == 1


def test_update_app_settings_updates_only_given_fields(test_db):
    db.update_app_settings(timezone="Europe/Paris", max_concurrent_runs=3)

    settings = db.get_app_settings()
    assert settings.timezone == "Europe/Paris"
    assert settings.max_concurrent_runs == 3
    assert settings.log_level == "INFO"   # inchangé


def test_app_settings_table_created_fresh_without_migration(tmp_path):
    """Table neuve — Base.metadata.create_all() doit suffire, sans bloc ALTER TABLE dans
    _migrate() (contrairement à l'ajout d'une colonne sur une table déjà existante)."""
    from sqlalchemy import create_engine, text

    db_path = tmp_path / "fresh_app_settings.db"
    db.init_db(db_path)
    cols = {r[1] for r in create_engine(f"sqlite:///{db_path}").connect()
            .execute(text("PRAGMA table_info(app_settings)")).fetchall()}
    assert "timezone" in cols
    assert "max_concurrent_runs" in cols

    db._engine = None
    db._SessionFactory = None


def test_migrate_adds_execution_mode_to_a_pre_existing_app_settings_table(tmp_path):
    """execution_mode ajouté par ALTER TABLE (chantier exécution en arrière-plan) — même patron
    que les colonnes resource_sample_* du chantier précédent : base pré-existante (avec toutes
    les autres colonnes déjà migrées) sans execution_mode, valeur par défaut 'IN_APP' appliquée
    par la migration."""
    from sqlalchemy import create_engine, text

    db_path = tmp_path / "legacy_app_settings.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE app_settings (
                id INTEGER PRIMARY KEY,
                timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
                misfire_grace_time_min INTEGER NOT NULL DEFAULT 60,
                coalesce_missed_runs BOOLEAN NOT NULL DEFAULT 1,
                max_concurrent_runs INTEGER NOT NULL DEFAULT 6,
                log_level VARCHAR(10) NOT NULL DEFAULT 'INFO',
                log_max_bytes INTEGER NOT NULL DEFAULT 5000000,
                log_backup_count INTEGER NOT NULL DEFAULT 5,
                dashboard_refresh_s INTEGER NOT NULL DEFAULT 30,
                pipelines_refresh_s INTEGER NOT NULL DEFAULT 30,
                live_log_refresh_s INTEGER NOT NULL DEFAULT 2,
                trace_glow_refresh_s INTEGER NOT NULL DEFAULT 2,
                resource_sample_interval_s INTEGER NOT NULL DEFAULT 60,
                resource_sample_retention_days INTEGER NOT NULL DEFAULT 7
            )
        """))
        conn.commit()

    db.init_db(db_path)
    cols = {r[1] for r in create_engine(f"sqlite:///{db_path}").connect()
            .execute(text("PRAGMA table_info(app_settings)")).fetchall()}
    assert "execution_mode" in cols
    assert db.get_app_settings().execution_mode == "IN_APP"

    db._engine = None
    db._SessionFactory = None


# ──────────────────────────────────────────────
#  FILE DE COMMANDES WORKER (chantier exécution en arrière-plan)
# ──────────────────────────────────────────────

def test_enqueue_and_consume_worker_command_cycle(test_db):
    cmd = db.enqueue_worker_command("RUN_NOW", {"pipeline_id": 42})
    assert cmd.id is not None
    assert cmd.consumed_at is None

    pending = db.get_pending_worker_commands()
    assert len(pending) == 1
    assert pending[0].command == "RUN_NOW"
    assert pending[0].payload_json == '{"pipeline_id": 42}'

    db.mark_worker_command_consumed(cmd.id)
    assert db.get_pending_worker_commands() == []


def test_enqueue_worker_command_without_payload(test_db):
    cmd = db.enqueue_worker_command("RELOAD")
    assert cmd.payload_json is None
    pending = db.get_pending_worker_commands()
    assert len(pending) == 1
    assert pending[0].command == "RELOAD"


def test_get_pending_worker_commands_orders_chronologically_and_excludes_consumed(test_db):
    first = db.enqueue_worker_command("RELOAD")
    second = db.enqueue_worker_command("SHUTDOWN")
    db.mark_worker_command_consumed(first.id)

    pending = db.get_pending_worker_commands()
    assert [c.id for c in pending] == [second.id]


def test_get_latest_resource_sample_returns_most_recent(test_db):
    from datetime import datetime, timedelta
    from database.models import ResourceSample

    assert db.get_latest_resource_sample() is None

    with db.get_session() as s:
        s.add(ResourceSample(timestamp=datetime.utcnow() - timedelta(minutes=5),
                              cpu_percent=1.0, memory_mb=100.0))
        s.add(ResourceSample(timestamp=datetime.utcnow(),
                              cpu_percent=9.0, memory_mb=200.0))

    latest = db.get_latest_resource_sample()
    assert latest.cpu_percent == 9.0


# ──────────────────────────────────────────────
#  PARALLÉLISME INTRA-PIPELINE (chantier dédié)
# ──────────────────────────────────────────────

def test_create_pipeline_defaults_parallel_execution_disabled(test_db):
    """Défaut False/4 pour tout pipeline — le parallélisme reste un choix explicite, jamais le
    comportement par défaut, même pour un pipeline tout juste créé."""
    p = db.create_pipeline(name="parallel-default-test")
    assert p.parallel_execution_enabled is False
    assert p.max_parallel_branches == 4


def test_update_run_active_steps_and_get_running_step_keys_multi_round_trip(test_db):
    pipeline = db.create_pipeline(name="active-steps-test")
    run = db.create_run(pipeline.id)

    assert db.get_running_step_keys_multi() == {}

    db.update_run_active_steps(run.id, {
        "a": {"label": "Étape A", "pct": 40},
        "b": {"label": "Étape B", "pct": 10},
    })

    result = db.get_running_step_keys_multi()
    assert result == {pipeline.id: {"a", "b"}}


def test_get_running_step_keys_multi_ignores_runs_without_active_steps(test_db):
    """Un run RUNNING dont active_steps_json est NULL (moteur linéaire/graphe séquentiel,
    jamais concurrent) ne doit jamais apparaître ici — get_running_step_keys() (singulier)
    reste la source pour ce cas."""
    pipeline = db.create_pipeline(name="active-steps-null-test")
    db.create_run(pipeline.id)

    assert db.get_running_step_keys_multi() == {}


def test_get_running_step_keys_multi_uses_most_recent_run_per_pipeline(test_db):
    from datetime import datetime, timedelta

    pipeline = db.create_pipeline(name="active-steps-multi-run-test")
    older = db.create_run(pipeline.id)
    db.update_run_active_steps(older.id, {"old": {"label": "Vieille étape", "pct": 50}})
    newer = db.create_run(pipeline.id)
    db.update_run_active_steps(newer.id, {"new": {"label": "Nouvelle étape", "pct": 20}})

    with db.get_session() as s:
        from database.models import PipelineRun
        s.get(PipelineRun, older.id).started_at = datetime.utcnow() - timedelta(minutes=5)
        s.get(PipelineRun, newer.id).started_at = datetime.utcnow()

    result = db.get_running_step_keys_multi()
    assert result == {pipeline.id: {"new"}}
