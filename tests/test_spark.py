"""
DataScheduler — tests/test_spark.py
Vérifie core/spark.py (étape SPARK_SQL) via de fausses classes paramiko (SSHClient/canal/SFTP) —
aucun cluster réel accessible depuis cet environnement, même principe de mock que
_FakeSqlConnector dans tests/test_step_reliability_fixes.py. Couvre : automatisation du prompt
kinit via pseudo-terminal, court-circuit propre sur échec Kerberos, exécution spark-sql
(succès/échec), rapatriement SFTP du résultat, nettoyage best-effort des fichiers temporaires
distants, fermeture systématique de la connexion SSH.
"""

import re
from pathlib import Path

import paramiko

import core.spark as spark


# ──────────────────────────────────────────────
#  Fausses classes paramiko
# ──────────────────────────────────────────────

class _FakeChannel:
    """Simule le canal d'un exec_command() : soit un prompt apparaît (kinit interactif), soit
    la commande se termine directement (kinit échoue avant tout prompt, ou spark-sql non
    interactif — pas de PTY, donc pas de prompt à attendre)."""

    def __init__(self, prompt_bytes: bytes = b"", exit_status: int = 0, has_prompt: bool = False):
        self._prompt_bytes = prompt_bytes
        self._exit_status = exit_status
        self._has_prompt = has_prompt
        self._delivered = False

    def recv_ready(self):
        return self._has_prompt and not self._delivered

    def recv(self, n):
        self._delivered = True
        data, self._prompt_bytes = self._prompt_bytes, b""
        return data

    def exit_status_ready(self):
        return (not self._has_prompt) or self._delivered

    def recv_exit_status(self):
        return self._exit_status


class _FakeStdin:
    def __init__(self):
        self.written = []

    def write(self, s):
        self.written.append(s)

    def flush(self):
        pass


class _FakeStdout:
    def __init__(self, channel, remaining: bytes = b""):
        self.channel = channel
        self._remaining = remaining

    def read(self):
        return self._remaining


class _FakeStderr:
    def __init__(self, remaining: bytes = b""):
        self._remaining = remaining

    def read(self):
        return self._remaining


class _FakeSftpFile:
    def __init__(self, files: dict, path: str, mode: str):
        self._files = files
        self._path = path

    def write(self, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self._files[self._path] = self._files.get(self._path, b"") + data

    def read(self, n=-1):
        content = self._files.get(self._path, b"")
        return content if n == -1 else content[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeSftp:
    def __init__(self, files: dict):
        self._files = files

    def open(self, path, mode="r"):
        return _FakeSftpFile(self._files, path, mode)

    def get(self, remote, local):
        Path(local).write_bytes(self._files.get(remote, b""))

    def close(self):
        pass


class _FakeSSHClient:
    """`exec_fn(cmd, get_pty, timeout) -> (stdin, stdout, stderr)` décide du comportement par
    commande — laisse le test scripter kinit vs. la commande spark-sql vs. le nettoyage."""

    def __init__(self, exec_fn, connect_should_fail: bool = False):
        self._exec_fn = exec_fn
        self._connect_should_fail = connect_should_fail
        self.closed = False
        self.exec_calls = []
        self.sftp_files: dict = {}

    def set_missing_host_key_policy(self, policy):
        pass

    def connect(self, hostname, port, username, password, timeout):
        if self._connect_should_fail:
            raise OSError("connexion refusée")

    def exec_command(self, cmd, get_pty=False, timeout=None):
        self.exec_calls.append(cmd)
        return self._exec_fn(cmd, get_pty=get_pty, timeout=timeout)

    def open_sftp(self):
        return _FakeSftp(self.sftp_files)

    def close(self):
        self.closed = True


def _ssh_cfg():
    return spark.SshExecConfig(host="edge01", port=22, username="jdupont", password="pwd")


def _krb_cfg():
    return spark.KerberosConfig(principal="jdupont@REALM.EXAMPLE", password="krbpwd")


def _install_fake_client(monkeypatch, client: _FakeSSHClient):
    monkeypatch.setattr(paramiko, "SSHClient", lambda: client)


# ──────────────────────────────────────────────
#  _kinit / test_kerberos_auth
# ──────────────────────────────────────────────

def test_kinit_succeeds_when_prompt_appears_and_exit_zero(monkeypatch):
    def exec_fn(cmd, get_pty=False, timeout=None):
        channel = _FakeChannel(prompt_bytes=b"Password for jdupont@REALM.EXAMPLE: ",
                                exit_status=0, has_prompt=True)
        return _FakeStdin(), _FakeStdout(channel), _FakeStderr()

    client = _FakeSSHClient(exec_fn)
    ok, message = spark._kinit(client, _krb_cfg())
    assert ok is True
    assert "réussi" in message


def test_kinit_fails_cleanly_on_nonzero_exit(monkeypatch):
    def exec_fn(cmd, get_pty=False, timeout=None):
        channel = _FakeChannel(prompt_bytes=b"Password for jdupont@REALM.EXAMPLE: ",
                                exit_status=1, has_prompt=True)
        return _FakeStdin(), _FakeStdout(channel, remaining=b"kinit: Preauthentication failed"), _FakeStderr()

    client = _FakeSSHClient(exec_fn)
    ok, message = spark._kinit(client, _krb_cfg())
    assert ok is False
    assert "Preauthentication" in message


def test_kinit_fails_cleanly_when_kinit_exits_before_any_prompt(monkeypatch):
    """Ex : principal inconnu — kinit échoue immédiatement, jamais de prompt de mot de passe."""
    def exec_fn(cmd, get_pty=False, timeout=None):
        channel = _FakeChannel(exit_status=1, has_prompt=False)
        return _FakeStdin(), _FakeStdout(channel, remaining=b"kinit: Client not found"), _FakeStderr()

    client = _FakeSSHClient(exec_fn)
    ok, message = spark._kinit(client, _krb_cfg())
    assert ok is False
    assert "Client not found" in message


def test_kinit_times_out_cleanly_when_prompt_never_appears(monkeypatch):
    monkeypatch.setattr(spark, "_KINIT_PROMPT_TIMEOUT_S", 0.2)

    class _StuckChannel(_FakeChannel):
        def recv_ready(self):
            return False

        def exit_status_ready(self):
            return False

    def exec_fn(cmd, get_pty=False, timeout=None):
        return _FakeStdin(), _FakeStdout(_StuckChannel()), _FakeStderr()

    client = _FakeSSHClient(exec_fn)
    ok, message = spark._kinit(client, _krb_cfg())
    assert ok is False
    assert "délai dépassé" in message


def test_test_kerberos_auth_closes_connection(monkeypatch):
    def exec_fn(cmd, get_pty=False, timeout=None):
        channel = _FakeChannel(prompt_bytes=b"Password: ", exit_status=0, has_prompt=True)
        return _FakeStdin(), _FakeStdout(channel), _FakeStderr()

    client = _FakeSSHClient(exec_fn)
    _install_fake_client(monkeypatch, client)

    result = spark.test_kerberos_auth(_ssh_cfg(), _krb_cfg())
    assert result.success is True
    assert client.closed is True


def test_test_ssh_connection_reports_failure_without_raising(monkeypatch):
    client = _FakeSSHClient(exec_fn=lambda *a, **kw: (None, None, None), connect_should_fail=True)
    _install_fake_client(monkeypatch, client)

    result = spark.test_ssh_connection(_ssh_cfg())
    assert result.success is False
    assert "refusée" in result.message


# ──────────────────────────────────────────────
#  run_spark_sql
# ──────────────────────────────────────────────

def _kinit_ok_exec_fn(cmd, get_pty=False, timeout=None):
    channel = _FakeChannel(prompt_bytes=b"Password: ", exit_status=0, has_prompt=True)
    return _FakeStdin(), _FakeStdout(channel), _FakeStderr()


def _make_dispatching_exec_fn(client: "_FakeSSHClient", spark_exit_status: int = 0,
                               spark_stderr: bytes = b""):
    """kinit (get_pty=True) réussit toujours ; toute autre commande (spark-sql, rm -f) répond
    selon spark_exit_status. Dépose spark_stderr dans le "fichier distant" 2> simulé
    (client.sftp_files) — _read_remote_file() lit via SFTP, pas via l'objet stderr
    d'exec_command(), exactement comme le ferait une vraie redirection shell `2>fichier`."""
    def exec_fn(cmd, get_pty=False, timeout=None):
        if get_pty:
            return _kinit_ok_exec_fn(cmd, get_pty=get_pty, timeout=timeout)
        if "spark-sql" in cmd and spark_stderr:
            m = re.search(r"2>(\S+)", cmd)
            if m:
                client.sftp_files[m.group(1)] = spark_stderr
        channel = _FakeChannel(exit_status=spark_exit_status, has_prompt=False)
        return _FakeStdin(), _FakeStdout(channel), _FakeStderr(remaining=spark_stderr)
    return exec_fn


def _make_client(spark_exit_status: int = 0, spark_stderr: bytes = b"",
                  remote_output_content: bytes | None = None) -> "_FakeSSHClient":
    """Construction en 2 temps (le canal a besoin du client pour écrire dans sftp_files, le
    client a besoin du canal pour son exec_fn) : client d'abord avec un exec_fn temporaire,
    remplacé une fois le client existe."""
    client = _FakeSSHClient(exec_fn=None)
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


def test_run_spark_sql_success_with_fetch_result(monkeypatch, tmp_path):
    client = _make_client(spark_exit_status=0, remote_output_content=b"col_a,col_b\n1,2\n")
    _install_fake_client(monkeypatch, client)

    local_out = tmp_path / "result.csv"
    result = spark.run_spark_sql(
        _ssh_cfg(), _krb_cfg(), spark_conf='--conf "spark.yarn.queue=default"',
        query="SELECT * FROM t", fetch_result=True, local_output_path=local_out,
    )

    assert result.success, result.error
    assert result.local_output_path == local_out
    assert local_out.read_text() == "col_a,col_b\n1,2\n"
    assert client.closed is True


def test_run_spark_sql_success_without_fetch_result_does_not_write_local_file(monkeypatch, tmp_path):
    client = _make_client(spark_exit_status=0)
    _install_fake_client(monkeypatch, client)

    local_out = tmp_path / "should_not_exist.csv"
    result = spark.run_spark_sql(
        _ssh_cfg(), _krb_cfg(), spark_conf="", query="INSERT INTO t VALUES (1)",
        fetch_result=False, local_output_path=local_out,
    )

    assert result.success, result.error
    assert result.local_output_path is None
    assert not local_out.exists()


def test_run_spark_sql_short_circuits_on_kinit_failure(monkeypatch, tmp_path):
    def exec_fn(cmd, get_pty=False, timeout=None):
        if get_pty:
            channel = _FakeChannel(prompt_bytes=b"Password: ", exit_status=1, has_prompt=True)
            return _FakeStdin(), _FakeStdout(channel, remaining=b"kinit: bad password"), _FakeStderr()
        raise AssertionError("spark-sql ne doit jamais être lancé si kinit a échoué")

    client = _FakeSSHClient(exec_fn)
    _install_fake_client(monkeypatch, client)

    result = spark.run_spark_sql(
        _ssh_cfg(), _krb_cfg(), spark_conf="", query="SELECT 1",
        fetch_result=False, local_output_path=tmp_path / "x.csv",
    )
    assert result.success is False
    assert "Authentification Kerberos" in result.error
    assert client.closed is True


def test_run_spark_sql_reports_nonzero_exit_status(monkeypatch, tmp_path):
    client = _make_client(spark_exit_status=1, spark_stderr=b"table not found")
    _install_fake_client(monkeypatch, client)

    result = spark.run_spark_sql(
        _ssh_cfg(), _krb_cfg(), spark_conf="", query="SELECT * FROM missing",
        fetch_result=False, local_output_path=tmp_path / "x.csv",
    )
    assert result.success is False
    assert "table not found" in result.error


def test_run_spark_sql_attempts_remote_cleanup_on_success_and_failure(monkeypatch, tmp_path):
    for exit_status in (0, 1):
        client = _make_client(spark_exit_status=exit_status)
        _install_fake_client(monkeypatch, client)
        spark.run_spark_sql(
            _ssh_cfg(), _krb_cfg(), spark_conf="", query="SELECT 1",
            fetch_result=False, local_output_path=tmp_path / "x.csv",
        )
        assert any(c.startswith("rm -f") for c in client.exec_calls), \
            f"pas de nettoyage tenté pour exit_status={exit_status}"


def test_run_spark_sql_closes_connection_even_on_unexpected_exception(monkeypatch, tmp_path):
    def exec_fn(cmd, get_pty=False, timeout=None):
        if get_pty:
            return _kinit_ok_exec_fn(cmd)
        raise RuntimeError("panne réseau inattendue")

    client = _FakeSSHClient(exec_fn)
    _install_fake_client(monkeypatch, client)

    result = spark.run_spark_sql(
        _ssh_cfg(), _krb_cfg(), spark_conf="", query="SELECT 1",
        fetch_result=False, local_output_path=tmp_path / "x.csv",
    )
    assert result.success is False
    assert "panne réseau" in result.error
    assert client.closed is True
