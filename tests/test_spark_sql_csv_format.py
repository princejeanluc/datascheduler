"""
DataScheduler — tests/test_spark_sql_csv_format.py
Configurabilité du fichier récupéré par SPARK_SQL (séparateur, encodage, guillemets — même
liberté que DB_EXTRACT, demandée explicitement par l'utilisateur après le correctif du libellé
"CSV-like"). spark-sql ne produit qu'un texte tabulé brut ; core.steps.spark_sql._rewrite_as_csv
le remet en forme selon la config de l'étape, avant publication dans ctx.output_file.
"""

import csv

import core.spark as spark_module
from core.steps.base import StepContext
from core.steps.spark_sql import SparkSqlStep, _rewrite_as_csv, _typed_for_quoting


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


# ──────────────────────────────────────────────
#  _rewrite_as_csv / _typed_for_quoting — unitaires, sans réseau
# ──────────────────────────────────────────────

def test_rewrite_uses_custom_separator(tmp_path):
    raw = tmp_path / "raw.tsv"
    raw.write_text("a\tb\n1\t2\n")
    out = tmp_path / "out.csv"

    _rewrite_as_csv(raw, out, separator="|", encoding="utf-8", quoting="QUOTE_MINIMAL")

    # read_text() normalise \r\n -> \n (universal newlines) ; le fichier contient bien \r\n
    # (terminateur de ligne par défaut du module csv), vérifié séparément via read_bytes().
    assert out.read_text() == "a|b\n1|2\n"
    assert out.read_bytes().endswith(b"1|2\r\n")


def test_rewrite_quote_all_wraps_every_field(tmp_path):
    raw = tmp_path / "raw.tsv"
    raw.write_text("a\tb\n1\t2\n")
    out = tmp_path / "out.csv"

    _rewrite_as_csv(raw, out, separator=",", encoding="utf-8", quoting="QUOTE_ALL")

    assert out.read_text() == '"a","b"\n"1","2"\n'


def test_rewrite_quote_nonnumeric_leaves_numbers_unquoted(tmp_path):
    """La sortie brute de spark-sql n'a aucun typage préservé — QUOTE_NONNUMERIC doit quand même
    reconnaître qu'un champ "1" est numérique, comme le ferait DB_EXTRACT sur un vrai DataFrame."""
    raw = tmp_path / "raw.tsv"
    raw.write_text("name\tcount\nalice\t3\n")
    out = tmp_path / "out.csv"

    _rewrite_as_csv(raw, out, separator=",", encoding="utf-8", quoting="QUOTE_NONNUMERIC")

    assert out.read_text() == '"name","count"\n"alice",3\n'


def test_rewrite_quote_none_uses_escapechar(tmp_path):
    raw = tmp_path / "raw.tsv"
    raw.write_text("a\tb\n1\t2\n")
    out = tmp_path / "out.csv"

    _rewrite_as_csv(raw, out, separator=",", encoding="utf-8", quoting="QUOTE_NONE")

    assert out.read_text() == "a,b\n1,2\n"


def test_rewrite_respects_custom_encoding(tmp_path):
    raw = tmp_path / "raw.tsv"
    raw.write_text("nom\tville\nÉtienne\tOrléans\n", encoding="utf-8")
    out = tmp_path / "out.csv"

    _rewrite_as_csv(raw, out, separator=";", encoding="latin-1", quoting="QUOTE_MINIMAL")

    assert out.read_bytes().decode("latin-1") == "nom;ville\r\nÉtienne;Orléans\r\n"


def test_typed_for_quoting_passthrough_when_not_quote_nonnumeric():
    assert _typed_for_quoting("3", csv.QUOTE_MINIMAL) == "3"


def test_typed_for_quoting_converts_int_and_float():
    assert _typed_for_quoting("3", csv.QUOTE_NONNUMERIC) == 3
    assert _typed_for_quoting("3.5", csv.QUOTE_NONNUMERIC) == 3.5
    assert _typed_for_quoting("alice", csv.QUOTE_NONNUMERIC) == "alice"


# ──────────────────────────────────────────────
#  SparkSqlStep — la config CSV de l'étape est bien appliquée de bout en bout
# ──────────────────────────────────────────────

def test_step_applies_configured_separator_and_quoting(test_db, monkeypatch):
    edge, krb = _base_profiles()
    from database import db_manager as db
    q = db.create_sql_query(name="Q1", sql_text="SELECT 1")

    def fake_run_spark_sql(ssh_cfg, krb_cfg, spark_conf, query, fetch_result,
                            local_output_path=None, timeout=3600, on_progress=None):
        local_output_path.write_text("a\tb\n1\t2\n")
        return _FakeSparkSqlResult(success=True, local_output_path=local_output_path)

    monkeypatch.setattr(spark_module, "run_spark_sql", fake_run_spark_sql)

    step = SparkSqlStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "sql_query_id": q.id,
        "fetch_result": True, "csv_separator": "|", "csv_encoding": "utf-8", "csv_quoting": "QUOTE_ALL",
    })
    ctx = StepContext()
    result = step.run(ctx)

    assert result.success, result.error
    assert ctx.output_file.read_text() == '"a"|"b"\n"1"|"2"\n'


def test_step_defaults_match_db_extract_style_defaults(test_db, monkeypatch):
    """Aucune config CSV fournie -> mêmes valeurs par défaut que DB_EXTRACT pour le séparateur
    et l'encodage (";" / "utf-8-sig"), pour rester familier à qui connaît déjà cette étape."""
    edge, krb = _base_profiles()
    from database import db_manager as db
    q = db.create_sql_query(name="Q1", sql_text="SELECT 1")

    def fake_run_spark_sql(ssh_cfg, krb_cfg, spark_conf, query, fetch_result,
                            local_output_path=None, timeout=3600, on_progress=None):
        local_output_path.write_text("a\tb\n1\t2\n")
        return _FakeSparkSqlResult(success=True, local_output_path=local_output_path)

    monkeypatch.setattr(spark_module, "run_spark_sql", fake_run_spark_sql)

    step = SparkSqlStep({
        "edge_profile_id": edge.id, "kerberos_profile_id": krb.id, "sql_query_id": q.id,
        "fetch_result": True,
    })
    ctx = StepContext()
    result = step.run(ctx)

    assert result.success, result.error
    with open(ctx.output_file, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert rows == [["a", "b"], ["1", "2"]]


# ──────────────────────────────────────────────
#  core.spark.run_spark_sql — en-tête auto-injecté quand fetch_result est vrai
# ──────────────────────────────────────────────

def _spark_sql_cmd(client) -> str:
    return next(c for c in client.exec_calls if "spark-sql" in c)


def test_header_conf_is_injected_when_fetch_result_true(monkeypatch, tmp_path):
    from tests.test_spark import _make_client
    from tests._fake_ssh import install_fake_client as _install_fake_client, ssh_cfg as _ssh_cfg, krb_cfg as _krb_cfg

    client = _make_client()
    _install_fake_client(monkeypatch, client)

    spark_module.run_spark_sql(
        _ssh_cfg(), _krb_cfg(), spark_conf="--conf spark.yarn.queue=default",
        query="SELECT 1", fetch_result=True, local_output_path=tmp_path / "out.tsv",
    )

    assert "spark.sql.cli.print.header=true" in _spark_sql_cmd(client)


def test_header_conf_not_injected_when_fetch_result_false(monkeypatch, tmp_path):
    from tests.test_spark import _make_client
    from tests._fake_ssh import install_fake_client as _install_fake_client, ssh_cfg as _ssh_cfg, krb_cfg as _krb_cfg

    client = _make_client()
    _install_fake_client(monkeypatch, client)

    spark_module.run_spark_sql(
        _ssh_cfg(), _krb_cfg(), spark_conf="", query="INSERT INTO t VALUES (1)",
        fetch_result=False, local_output_path=tmp_path / "out.tsv",
    )

    assert "spark.sql.cli.print.header" not in _spark_sql_cmd(client)


def test_header_conf_not_duplicated_if_user_already_set_it(monkeypatch, tmp_path):
    from tests.test_spark import _make_client
    from tests._fake_ssh import install_fake_client as _install_fake_client, ssh_cfg as _ssh_cfg, krb_cfg as _krb_cfg

    client = _make_client()
    _install_fake_client(monkeypatch, client)

    spark_module.run_spark_sql(
        _ssh_cfg(), _krb_cfg(), spark_conf="--conf spark.sql.cli.print.header=false",
        query="SELECT 1", fetch_result=True, local_output_path=tmp_path / "out.tsv",
    )

    cmd = _spark_sql_cmd(client)
    assert cmd.count("spark.sql.cli.print.header") == 1
    assert "spark.sql.cli.print.header=false" in cmd
