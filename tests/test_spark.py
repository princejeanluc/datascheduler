"""
DataScheduler — tests/test_spark.py
Vérifie core/spark.py::run_spark_sql() (étape SPARK_SQL) via de fausses classes paramiko
(tests/_fake_ssh.py) — aucun cluster réel accessible depuis cet environnement, même principe de
mock que _FakeSqlConnector dans tests/test_step_reliability_fixes.py. Couvre : exécution
spark-sql (succès/échec), rapatriement SFTP du résultat, nettoyage best-effort des fichiers
temporaires distants, fermeture systématique de la connexion SSH.

Les tests de la mécanique SSH/kinit elle-même (partagée avec SQOOP_EXPORT depuis le chantier K)
ont déménagé dans tests/test_hadoop_edge.py, avec le code qu'ils testent.
"""

import re

import core.spark as spark
from tests._fake_ssh import (
    FakeChannel, FakeStdin, FakeStdout, FakeStderr, FakeSSHClient,
    ssh_cfg, krb_cfg, install_fake_client,
)


def _kinit_ok_exec_fn(cmd, get_pty=False, timeout=None):
    channel = FakeChannel(prompt_bytes=b"Password: ", exit_status=0, has_prompt=True)
    return FakeStdin(), FakeStdout(channel), FakeStderr()


def _make_dispatching_exec_fn(client: "FakeSSHClient", spark_exit_status: int = 0,
                               spark_stderr: bytes = b""):
    """kinit (get_pty=True) réussit toujours ; toute autre commande (spark-sql, rm -f) répond
    selon spark_exit_status. Dépose spark_stderr dans le "fichier distant" 2> simulé
    (client.sftp_files) — read_remote_file() lit via SFTP, pas via l'objet stderr
    d'exec_command(), exactement comme le ferait une vraie redirection shell `2>fichier`."""
    def exec_fn(cmd, get_pty=False, timeout=None):
        if get_pty:
            return _kinit_ok_exec_fn(cmd, get_pty=get_pty, timeout=timeout)
        if "spark-sql" in cmd and spark_stderr:
            m = re.search(r"2>(\S+)", cmd)
            if m:
                client.sftp_files[m.group(1)] = spark_stderr
        channel = FakeChannel(exit_status=spark_exit_status, has_prompt=False)
        return FakeStdin(), FakeStdout(channel), FakeStderr(remaining=spark_stderr)
    return exec_fn


def _make_client(spark_exit_status: int = 0, spark_stderr: bytes = b"",
                  remote_output_content: bytes | None = None) -> "FakeSSHClient":
    """Construction en 2 temps (le canal a besoin du client pour écrire dans sftp_files, le
    client a besoin du canal pour son exec_fn) : client d'abord avec un exec_fn temporaire,
    remplacé une fois le client existe."""
    client = FakeSSHClient(exec_fn=None)
    base_fn = _make_dispatching_exec_fn(client, spark_exit_status=spark_exit_status,
                                         spark_stderr=spark_stderr)
    if remote_output_content is None:
        client._exec_fn = base_fn
    else:
        def exec_fn(cmd, get_pty=False, timeout=None):
            if not get_pty and "spark-sql" in cmd:
                m = re.search(r">\s*(\S+)\s+2>", cmd)
                if m:
                    client.sftp_files[m.group(1)] = remote_output_content
            return base_fn(cmd, get_pty=get_pty, timeout=timeout)
        client._exec_fn = exec_fn
    return client


def test_run_spark_sql_reports_phase_ticks_with_fetch_result(monkeypatch, tmp_path):
    """chantier O : le tick avant exec_command() ("Exécution de la requête sur le cluster…")
    est le point critique — c'est celui qui manquait pour distinguer un kinit bloqué d'une
    requête réellement en cours pendant plusieurs minutes."""
    client = _make_client(spark_exit_status=0, remote_output_content=b"a,b\n1,2\n")
    install_fake_client(monkeypatch, client)
    ticks = []

    result = spark.run_spark_sql(
        ssh_cfg(), krb_cfg(), spark_conf="", query="SELECT * FROM t", fetch_result=True,
        local_output_path=tmp_path / "out.csv",
        on_progress=lambda msg, pct: ticks.append((msg, pct)),
    )

    assert result.success, result.error
    messages = [m for m, _ in ticks]
    assert messages == [
        "Connexion au nœud edge…",
        "Authentification Kerberos…",
        "Envoi de la requête…",
        "Exécution de la requête sur le cluster…",
        "Récupération du résultat…",
    ]
    pcts = [p for _, p in ticks]
    assert pcts == sorted(pcts)


def test_run_spark_sql_skips_fetch_tick_without_fetch_result(monkeypatch):
    client = _make_client(spark_exit_status=0)
    install_fake_client(monkeypatch, client)
    ticks = []

    spark.run_spark_sql(
        ssh_cfg(), krb_cfg(), spark_conf="", query="INSERT INTO t VALUES (1)",
        fetch_result=False, on_progress=lambda msg, pct: ticks.append((msg, pct)),
    )

    messages = [m for m, _ in ticks]
    assert "Récupération du résultat…" not in messages
    assert messages[-1] == "Exécution de la requête sur le cluster…"


def test_run_spark_sql_success_with_fetch_result(monkeypatch, tmp_path):
    client = _make_client(spark_exit_status=0, remote_output_content=b"col_a,col_b\n1,2\n")
    install_fake_client(monkeypatch, client)

    local_out = tmp_path / "result.csv"
    result = spark.run_spark_sql(
        ssh_cfg(), krb_cfg(), spark_conf='--conf "spark.yarn.queue=default"',
        query="SELECT * FROM t", fetch_result=True, local_output_path=local_out,
    )

    assert result.success, result.error
    assert result.local_output_path == local_out
    assert local_out.read_text() == "col_a,col_b\n1,2\n"
    assert client.closed is True


def test_run_spark_sql_success_without_fetch_result_does_not_write_local_file(monkeypatch, tmp_path):
    client = _make_client(spark_exit_status=0)
    install_fake_client(monkeypatch, client)

    local_out = tmp_path / "should_not_exist.csv"
    result = spark.run_spark_sql(
        ssh_cfg(), krb_cfg(), spark_conf="", query="INSERT INTO t VALUES (1)",
        fetch_result=False, local_output_path=local_out,
    )

    assert result.success, result.error
    assert result.local_output_path is None
    assert not local_out.exists()


def test_run_spark_sql_short_circuits_on_kinit_failure(monkeypatch, tmp_path):
    def exec_fn(cmd, get_pty=False, timeout=None):
        if get_pty:
            channel = FakeChannel(prompt_bytes=b"Password: ", exit_status=1, has_prompt=True)
            return FakeStdin(), FakeStdout(channel, remaining=b"kinit: bad password"), FakeStderr()
        raise AssertionError("spark-sql ne doit jamais être lancé si kinit a échoué")

    client = FakeSSHClient(exec_fn)
    install_fake_client(monkeypatch, client)

    result = spark.run_spark_sql(
        ssh_cfg(), krb_cfg(), spark_conf="", query="SELECT 1",
        fetch_result=False, local_output_path=tmp_path / "x.csv",
    )
    assert result.success is False
    assert "Authentification Kerberos" in result.error
    assert client.closed is True


def test_run_spark_sql_reports_nonzero_exit_status(monkeypatch, tmp_path):
    client = _make_client(spark_exit_status=1, spark_stderr=b"table not found")
    install_fake_client(monkeypatch, client)

    result = spark.run_spark_sql(
        ssh_cfg(), krb_cfg(), spark_conf="", query="SELECT * FROM missing",
        fetch_result=False, local_output_path=tmp_path / "x.csv",
    )
    assert result.success is False
    assert "table not found" in result.error


def test_run_spark_sql_attempts_remote_cleanup_on_success_and_failure(monkeypatch, tmp_path):
    for exit_status in (0, 1):
        client = _make_client(spark_exit_status=exit_status)
        install_fake_client(monkeypatch, client)
        spark.run_spark_sql(
            ssh_cfg(), krb_cfg(), spark_conf="", query="SELECT 1",
            fetch_result=False, local_output_path=tmp_path / "x.csv",
        )
        assert any(c.startswith("rm -f") for c in client.exec_calls), \
            f"pas de nettoyage tenté pour exit_status={exit_status}"


def test_run_spark_sql_closes_connection_even_on_unexpected_exception(monkeypatch, tmp_path):
    def exec_fn(cmd, get_pty=False, timeout=None):
        if get_pty:
            return _kinit_ok_exec_fn(cmd)
        raise RuntimeError("panne réseau inattendue")

    client = FakeSSHClient(exec_fn)
    install_fake_client(monkeypatch, client)

    result = spark.run_spark_sql(
        ssh_cfg(), krb_cfg(), spark_conf="", query="SELECT 1",
        fetch_result=False, local_output_path=tmp_path / "x.csv",
    )
    assert result.success is False
    assert "panne réseau" in result.error
    assert client.closed is True
