"""
DataScheduler — tests/test_hadoop_edge.py
Vérifie core/hadoop_edge.py (chantier K — extrait de core/spark.py pour être partagé avec
SQOOP_EXPORT) via de fausses classes paramiko (tests/_fake_ssh.py) — aucun cluster réel
accessible depuis cet environnement. Couvre : automatisation du prompt kinit via
pseudo-terminal, court-circuit propre sur échec Kerberos, fermeture systématique de la
connexion SSH. Anciennement dans tests/test_spark.py — déplacé avec le code qu'il teste.
"""

import core.hadoop_edge as hadoop_edge
from tests._fake_ssh import (
    FakeChannel, FakeStdin, FakeStdout, FakeStderr, FakeSSHClient,
    ssh_cfg, krb_cfg, install_fake_client,
)


def test_kinit_succeeds_when_prompt_appears_and_exit_zero(monkeypatch):
    def exec_fn(cmd, get_pty=False, timeout=None):
        channel = FakeChannel(prompt_bytes=b"Password for jdupont@REALM.EXAMPLE: ",
                               exit_status=0, has_prompt=True)
        return FakeStdin(), FakeStdout(channel), FakeStderr()

    client = FakeSSHClient(exec_fn)
    ok, message = hadoop_edge._kinit(client, krb_cfg())
    assert ok is True
    assert "réussi" in message


def test_kinit_fails_cleanly_on_nonzero_exit(monkeypatch):
    def exec_fn(cmd, get_pty=False, timeout=None):
        channel = FakeChannel(prompt_bytes=b"Password for jdupont@REALM.EXAMPLE: ",
                               exit_status=1, has_prompt=True)
        return FakeStdin(), FakeStdout(channel, remaining=b"kinit: Preauthentication failed"), FakeStderr()

    client = FakeSSHClient(exec_fn)
    ok, message = hadoop_edge._kinit(client, krb_cfg())
    assert ok is False
    assert "Preauthentication" in message


def test_kinit_fails_cleanly_when_kinit_exits_before_any_prompt(monkeypatch):
    """Ex : principal inconnu — kinit échoue immédiatement, jamais de prompt de mot de passe."""
    def exec_fn(cmd, get_pty=False, timeout=None):
        channel = FakeChannel(exit_status=1, has_prompt=False)
        return FakeStdin(), FakeStdout(channel, remaining=b"kinit: Client not found"), FakeStderr()

    client = FakeSSHClient(exec_fn)
    ok, message = hadoop_edge._kinit(client, krb_cfg())
    assert ok is False
    assert "Client not found" in message


def test_kinit_times_out_cleanly_when_prompt_never_appears(monkeypatch):
    monkeypatch.setattr(hadoop_edge, "_KINIT_PROMPT_TIMEOUT_S", 0.2)

    class _StuckChannel(FakeChannel):
        def recv_ready(self):
            return False

        def exit_status_ready(self):
            return False

    def exec_fn(cmd, get_pty=False, timeout=None):
        return FakeStdin(), FakeStdout(_StuckChannel()), FakeStderr()

    client = FakeSSHClient(exec_fn)
    ok, message = hadoop_edge._kinit(client, krb_cfg())
    assert ok is False
    assert "délai dépassé" in message


def test_test_kerberos_auth_closes_connection(monkeypatch):
    def exec_fn(cmd, get_pty=False, timeout=None):
        channel = FakeChannel(prompt_bytes=b"Password: ", exit_status=0, has_prompt=True)
        return FakeStdin(), FakeStdout(channel), FakeStderr()

    client = FakeSSHClient(exec_fn)
    install_fake_client(monkeypatch, client)

    result = hadoop_edge.test_kerberos_auth(ssh_cfg(), krb_cfg())
    assert result.success is True
    assert client.closed is True


def test_test_ssh_connection_reports_failure_without_raising(monkeypatch):
    client = FakeSSHClient(exec_fn=lambda *a, **kw: (None, None, None), connect_should_fail=True)
    install_fake_client(monkeypatch, client)

    result = hadoop_edge.test_ssh_connection(ssh_cfg())
    assert result.success is False
    assert "refusée" in result.message
