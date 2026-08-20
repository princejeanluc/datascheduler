"""
DataScheduler — tests/test_spark_sql_step.py
Vérifie SparkSqlStep.run() (chantier Spark SQL, D.3) — core.spark.run_spark_sql est monkeypatché
directement (pas besoin de redescendre jusqu'aux fakes paramiko, déjà couverts par
tests/test_spark.py) : résolution des 3 références, résolution des jetons, publication du
résultat sous ctx.output_file/output_name, nettoyage du fichier temporaire local sur échec.
"""

import core.spark as spark_module
from core.steps.base import StepContext
from core.steps.spark_sql import SparkSqlStep


class _FakeSparkSqlResult:
    def __init__(self, success=True, error="", local_output_path=None, duration_s=1.0):
        self.success = success
        self.error = error
        self.local_output_path = local_output_path
        self.duration_s = duration_s


def _base_profiles():
    from database import db_manager as db
    edge = db.create_ssh_profile(name="EDGE01", host="edge01", port=22, username="u", password="p")
    krb  = db.create_kerberos_profile(name="KRB1", principal="u@REALM", password="p")
    return edge, krb


def test_success_with_fetch_result_sets_output_file_and_named_artifact(test_db, monkeypatch, tmp_path):
    edge, krb = _base_profiles()
    from database import db_manager as db
    q = db.create_sql_query(name="Q1", sql_text="SELECT 1")

    captured = {}

    def fake_run_spark_sql(ssh_cfg, krb_cfg, spark_conf, query, fetch_result,
                            local_output_path=None, timeout=3600, on_progress=None, cancel_event=None):
        captured["fetch_result"] = fetch_result
        captured["raw_output_path"] = local_output_path
        # Sortie brute simulée de spark-sql : tabulée, sans guillemets.
        local_output_path.write_text("a\tb\n1\t2\n")
        return _FakeSparkSqlResult(success=True, local_output_path=local_output_path)

    monkeypatch.setattr(spark_module, "run_spark_sql", fake_run_spark_sql)

    step = SparkSqlStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "sql_query_id": q.id,
        "fetch_result": True, "output_name": "spark_result",
    })
    ctx = StepContext()
    result = step.run(ctx)

    assert result.success, result.error
    assert captured["fetch_result"] is True
    # Le step publie un fichier reformaté (.csv), distinct du fichier brut téléchargé (.tsv),
    # qui est nettoyé une fois la mise en forme terminée.
    assert ctx.output_file != captured["raw_output_path"]
    assert ctx.output_file.suffix == ".csv"
    assert not captured["raw_output_path"].exists()
    assert ctx.artifacts["spark_result"] == ctx.output_file

    import csv
    with open(ctx.output_file, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f, delimiter=";"))   # séparateur par défaut, comme DB_EXTRACT
    assert rows == [["a", "b"], ["1", "2"]]


def test_run_passes_on_progress_through_to_run_spark_sql(test_db, monkeypatch, tmp_path):
    """chantier O : le step ne devine plus les phases lui-même — il relaie tel quel
    l'on_progress reçu à run_spark_sql(), qui seul connaît les vraies phases bloquantes."""
    edge, krb = _base_profiles()
    from database import db_manager as db
    q = db.create_sql_query(name="Q1", sql_text="SELECT 1")

    captured = {}

    def fake_run_spark_sql(ssh_cfg, krb_cfg, spark_conf, query, fetch_result,
                            local_output_path=None, timeout=3600, on_progress=None, cancel_event=None):
        captured["on_progress"] = on_progress
        if on_progress:
            on_progress("Exécution de la requête sur le cluster…", 40)
        return _FakeSparkSqlResult(success=True, local_output_path=None)

    monkeypatch.setattr(spark_module, "run_spark_sql", fake_run_spark_sql)

    ticks = []
    step = SparkSqlStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "sql_query_id": q.id,
        "fetch_result": False,
    })
    result = step.run(StepContext(), on_progress=lambda msg, pct: ticks.append((msg, pct)))

    assert result.success, result.error
    assert captured["on_progress"] is not None
    assert ("Exécution de la requête sur le cluster…", 40) in ticks


def test_success_without_fetch_result_does_not_touch_output_file(test_db, monkeypatch):
    edge, krb = _base_profiles()
    from database import db_manager as db
    q = db.create_sql_query(name="Q1", sql_text="INSERT INTO t VALUES (1)")

    captured = {}

    def fake_run_spark_sql(ssh_cfg, krb_cfg, spark_conf, query, fetch_result,
                            local_output_path=None, timeout=3600, on_progress=None, cancel_event=None):
        captured["local_output_path"] = local_output_path
        return _FakeSparkSqlResult(success=True, local_output_path=None)

    monkeypatch.setattr(spark_module, "run_spark_sql", fake_run_spark_sql)

    step = SparkSqlStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "sql_query_id": q.id,
        "fetch_result": False,
    })
    ctx = StepContext()
    result = step.run(ctx)

    assert result.success, result.error
    assert captured["local_output_path"] is None   # jamais créé quand fetch_result=False
    assert ctx.output_file is None
    assert ctx.artifacts == {}


def test_resolves_tokens_in_spark_conf_and_query(test_db, monkeypatch):
    edge, krb = _base_profiles()
    from database import db_manager as db
    q = db.create_sql_query(name="Q1", sql_text="SELECT * FROM t WHERE dt = '{yyyyMMdd}'")

    captured = {}

    def fake_run_spark_sql(ssh_cfg, krb_cfg, spark_conf, query, fetch_result,
                            local_output_path=None, timeout=3600, on_progress=None, cancel_event=None):
        captured["spark_conf"] = spark_conf
        captured["query"] = query
        return _FakeSparkSqlResult(success=True)

    monkeypatch.setattr(spark_module, "run_spark_sql", fake_run_spark_sql)

    step = SparkSqlStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "sql_query_id": q.id,
        "fetch_result": False, "spark_conf": "--conf spark.run.date={yyyyMMdd}",
    })
    step.run(StepContext())

    from datetime import datetime
    today = datetime.now().strftime("%Y%m%d")
    assert "{yyyyMMdd}" not in captured["query"]
    assert today in captured["query"]
    assert today in captured["spark_conf"]


def test_missing_edge_profile_fails_cleanly(test_db):
    _, krb = _base_profiles()
    from database import db_manager as db
    q = db.create_sql_query(name="Q1", sql_text="SELECT 1")

    step = SparkSqlStep({
        "edge_profile_id": 999999, "kerberos_profile_id": krb.id, "sql_query_id": q.id,
        "fetch_result": False,
    })
    result = step.run(StepContext())
    assert result.success is False
    assert "SSH" in result.error


def test_missing_kerberos_profile_fails_cleanly(test_db):
    edge, _ = _base_profiles()
    from database import db_manager as db
    q = db.create_sql_query(name="Q1", sql_text="SELECT 1")

    step = SparkSqlStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": 999999, "sql_query_id": q.id,
        "fetch_result": False,
    })
    result = step.run(StepContext())
    assert result.success is False
    assert "Kerberos" in result.error


def test_missing_sql_query_fails_cleanly(test_db):
    edge, krb = _base_profiles()
    step = SparkSqlStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "sql_query_id": 999999,
        "fetch_result": False,
    })
    result = step.run(StepContext())
    assert result.success is False
    assert "Requête SQL" in result.error


def test_failure_cleans_up_local_temp_file(test_db, monkeypatch):
    edge, krb = _base_profiles()
    from database import db_manager as db
    q = db.create_sql_query(name="Q1", sql_text="SELECT 1")

    captured = {}

    def fake_run_spark_sql(ssh_cfg, krb_cfg, spark_conf, query, fetch_result,
                            local_output_path=None, timeout=3600, on_progress=None, cancel_event=None):
        captured["local_output_path"] = local_output_path
        return _FakeSparkSqlResult(success=False, error="spark-sql a échoué")

    monkeypatch.setattr(spark_module, "run_spark_sql", fake_run_spark_sql)

    step = SparkSqlStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "sql_query_id": q.id,
        "fetch_result": True,
    })
    result = step.run(StepContext())

    assert result.success is False
    assert result.error == "spark-sql a échoué"
    assert not captured["local_output_path"].exists()
