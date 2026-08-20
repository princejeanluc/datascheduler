"""
DataScheduler — tests/test_sqoop_run.py
Vérifie core.sqoop.run_sqoop_export()/build_sqoop_export_command() via de fausses classes
paramiko (tests/_fake_ssh.py) — même principe que tests/test_spark.py. Couvre : commande bien
formée, court-circuit propre sur échec Kerberos, échec propre sur code de sortie non nul,
masquage du mot de passe pour la journalisation, nettoyage/fermeture systématiques.
"""

import threading

import core.sqoop as sqoop_module
from core.sql_db import SqlDbConfig
from core.sqoop import build_sqoop_export_command, run_sqoop_export
from tests._fake_ssh import (
    FakeBlockingChannel, FakeChannel, FakeStdin, FakeStdout, FakeStderr, FakeSSHClient,
    ssh_cfg, krb_cfg, elevation_cfg, install_fake_client,
)


def _oracle_cfg():
    return SqlDbConfig(db_type="ORACLE", host="10.0.0.5", port=1521, username="ORAUSER",
                        password="s3cr3t", service_name="PRODDB")


def _kinit_ok_exec_fn(cmd, get_pty=False, timeout=None):
    channel = FakeChannel(prompt_bytes=b"Password: ", exit_status=0, has_prompt=True)
    return FakeStdin(), FakeStdout(channel), FakeStderr()


def _make_client(sqoop_exit_status: int = 0, sqoop_stderr: bytes = b"") -> FakeSSHClient:
    def exec_fn(cmd, get_pty=False, timeout=None):
        if get_pty:
            return _kinit_ok_exec_fn(cmd, get_pty=get_pty, timeout=timeout)
        if "sqoop export" in cmd and sqoop_stderr:
            import re
            m = re.search(r"2>(\S+)", cmd)
            if m:
                client.sftp_files[m.group(1)] = sqoop_stderr
        channel = FakeChannel(exit_status=sqoop_exit_status, has_prompt=False)
        return FakeStdin(), FakeStdout(channel), FakeStderr(remaining=sqoop_stderr)
    client = FakeSSHClient(exec_fn)
    return client


def test_build_sqoop_export_command_masked_hides_password():
    cmd_real = build_sqoop_export_command(
        "jdbc:oracle:thin:@...", "ORAUSER", "s3cr3t",
        "DD", "FINAL_EQUIPEMENT_CLIENT", "xxx.xxxxx", "", masked=False,
    )
    cmd_masked = build_sqoop_export_command(
        "jdbc:oracle:thin:@...", "ORAUSER", "s3cr3t",
        "DD", "FINAL_EQUIPEMENT_CLIENT", "xxx.xxxxx", "", masked=True,
    )
    assert "s3cr3t" in cmd_real
    assert "s3cr3t" not in cmd_masked
    assert "****" in cmd_masked
    assert "--hcatalog-table FINAL_EQUIPEMENT_CLIENT" in cmd_real
    assert "--hcatalog-database DD" in cmd_real
    assert "--table xxx.xxxxx" in cmd_real
    assert "-jt local" in cmd_real


def test_run_sqoop_export_success(monkeypatch):
    client = _make_client(sqoop_exit_status=0)
    install_fake_client(monkeypatch, client)

    result = run_sqoop_export(
        ssh_cfg(), krb_cfg(), _oracle_cfg(),
        "DD", "FINAL_EQUIPEMENT_CLIENT", "xxx.xxxxx", "",
    )

    assert result.success, result.error
    assert client.closed is True
    assert any(c.startswith("rm -f") for c in client.exec_calls)


def test_run_sqoop_export_short_circuits_on_kinit_failure(monkeypatch):
    def exec_fn(cmd, get_pty=False, timeout=None):
        if get_pty:
            channel = FakeChannel(prompt_bytes=b"Password: ", exit_status=1, has_prompt=True)
            return FakeStdin(), FakeStdout(channel, remaining=b"kinit: bad password"), FakeStderr()
        raise AssertionError("sqoop ne doit jamais être lancé si kinit a échoué")

    client = FakeSSHClient(exec_fn)
    install_fake_client(monkeypatch, client)

    result = run_sqoop_export(
        ssh_cfg(), krb_cfg(), _oracle_cfg(), "DD", "T", "xxx.t", "",
    )
    assert not result.success
    assert "Authentification Kerberos" in result.error
    assert client.closed is True


def test_run_sqoop_export_reports_nonzero_exit_status(monkeypatch):
    client = _make_client(sqoop_exit_status=1, sqoop_stderr=b"ORA-00942: table or view does not exist")
    install_fake_client(monkeypatch, client)

    result = run_sqoop_export(
        ssh_cfg(), krb_cfg(), _oracle_cfg(), "DD", "T", "xxx.t", "",
    )
    assert not result.success
    assert "ORA-00942" in result.error


def test_run_sqoop_export_never_leaks_password_in_result_error(monkeypatch):
    client = _make_client(sqoop_exit_status=1, sqoop_stderr=b"connection refused")
    install_fake_client(monkeypatch, client)

    result = run_sqoop_export(
        ssh_cfg(), krb_cfg(), _oracle_cfg(), "DD", "T", "xxx.t", "",
    )
    assert "s3cr3t" not in result.error


def test_run_sqoop_export_skips_kinit_entirely_when_krb_cfg_is_none(monkeypatch):
    """Chantier L : certaines équipes n'utilisent pas Kerberos pour Sqoop du tout — krb_cfg=None
    ne doit jamais déclencher kinit (aucun exec_command avec get_pty=True)."""
    def exec_fn(cmd, get_pty=False, timeout=None):
        assert not get_pty, "kinit ne doit jamais être tenté quand krb_cfg est None"
        channel = FakeChannel(exit_status=0, has_prompt=False)
        return FakeStdin(), FakeStdout(channel), FakeStderr()

    client = FakeSSHClient(exec_fn)
    install_fake_client(monkeypatch, client)

    result = run_sqoop_export(
        ssh_cfg(), None, _oracle_cfg(), "DD", "T", "xxx.t", "",
    )

    assert result.success, result.error


def test_run_sqoop_export_reports_phase_ticks_on_historical_path(monkeypatch):
    """chantier O : le tick avant exec_command() ("Export Sqoop en cours…") est le point
    critique — jusqu'ici rien ne distinguait "kinit en cours" de "sqoop tourne déjà"."""
    client = _make_client(sqoop_exit_status=0)
    install_fake_client(monkeypatch, client)
    ticks = []

    result = run_sqoop_export(
        ssh_cfg(), krb_cfg(), _oracle_cfg(), "DD", "T", "xxx.t", "",
        on_progress=lambda msg, pct: ticks.append((msg, pct)),
    )

    assert result.success, result.error
    messages = [m for m, _ in ticks]
    assert messages == [
        "Connexion au nœud edge…",
        "Authentification Kerberos…",
        "Export Sqoop en cours…",
    ]
    pcts = [p for _, p in ticks]
    assert pcts == sorted(pcts)


def test_run_sqoop_export_skips_kerberos_tick_when_krb_cfg_is_none(monkeypatch):
    client = _make_client(sqoop_exit_status=0)
    install_fake_client(monkeypatch, client)
    ticks = []

    run_sqoop_export(
        ssh_cfg(), None, _oracle_cfg(), "DD", "T", "xxx.t", "",
        on_progress=lambda msg, pct: ticks.append((msg, pct)),
    )

    messages = [m for m, _ in ticks]
    assert "Authentification Kerberos…" not in messages


def test_run_sqoop_export_delegates_to_elevation_path_when_configured(monkeypatch):
    """elevation_cfg fourni → le chemin exec_command/kinit classique n'est jamais emprunté,
    tout passe par core.hadoop_edge.run_command_with_elevation (déjà testé en détail dans
    tests/test_hadoop_edge_elevation.py — ici on vérifie seulement le bon aiguillage/passage
    des paramètres)."""
    captured = {}

    def fake_run_command_with_elevation(ssh_cfg_arg, command, timeout, elevation_cfg=None,
                                         krb_cfg=None, on_progress=None, cancel_event=None):
        captured["command"] = command
        captured["elevation_cfg"] = elevation_cfg
        captured["krb_cfg"] = krb_cfg
        captured["on_progress"] = on_progress
        return True, "ok"

    monkeypatch.setattr(sqoop_module, "run_command_with_elevation", fake_run_command_with_elevation)

    marker = lambda msg, pct: None
    result = run_sqoop_export(
        ssh_cfg(), krb_cfg(), _oracle_cfg(), "DD", "T", "xxx.t", "",
        elevation_cfg=elevation_cfg(), on_progress=marker,
    )

    assert result.success, result.error
    assert captured["elevation_cfg"].target_user == "nifi"
    assert captured["krb_cfg"] is not None
    # chantier O : on_progress doit être transmis tel quel au chemin élévation, qui a déjà ses
    # propres ticks (testés dans tests/test_hadoop_edge_elevation.py).
    assert captured["on_progress"] is marker
    assert "sqoop export" in captured["command"]


def test_run_sqoop_export_elevation_path_reports_failure(monkeypatch):
    def fake_run_command_with_elevation(ssh_cfg_arg, command, timeout, elevation_cfg=None,
                                         krb_cfg=None, on_progress=None, cancel_event=None):
        return False, "sudo su : délai dépassé en attendant l'invite de mot de passe."

    monkeypatch.setattr(sqoop_module, "run_command_with_elevation", fake_run_command_with_elevation)

    result = run_sqoop_export(
        ssh_cfg(), None, _oracle_cfg(), "DD", "T", "xxx.t", "",
        elevation_cfg=elevation_cfg(),
    )

    assert not result.success
    assert "délai dépassé" in result.error


def test_run_sqoop_export_forwards_cancel_event_to_elevation_path(monkeypatch):
    captured = {}

    def fake_run_command_with_elevation(ssh_cfg_arg, command, timeout, elevation_cfg=None,
                                         krb_cfg=None, on_progress=None, cancel_event=None):
        captured["cancel_event"] = cancel_event
        return True, "ok"

    monkeypatch.setattr(sqoop_module, "run_command_with_elevation", fake_run_command_with_elevation)

    sentinel_event = threading.Event()
    run_sqoop_export(
        ssh_cfg(), None, _oracle_cfg(), "DD", "T", "xxx.t", "",
        elevation_cfg=elevation_cfg(), cancel_event=sentinel_event,
    )

    assert captured["cancel_event"] is sentinel_event


def test_run_sqoop_export_unblocks_and_reports_cancelled_on_historical_path(monkeypatch):
    """Chemin sans élévation : l'authentification Kerberos réussit, la commande sqoop reste
    indéfiniment "en cours" (canal bloquant) — cancel_event positionné une fois l'attente
    réellement démarrée, vérifie que le thread sentinelle (core.hadoop_edge.watch_cancel) ferme
    le canal et débloque l'appel plutôt que d'attendre le timeout distant."""
    blocking_channel = FakeBlockingChannel()

    def exec_fn(cmd, get_pty=False, timeout=None):
        if get_pty:
            return _kinit_ok_exec_fn(cmd, get_pty=get_pty, timeout=timeout)
        return FakeStdin(), FakeStdout(blocking_channel), FakeStderr()

    client = FakeSSHClient(exec_fn)
    install_fake_client(monkeypatch, client)
    cancel_event = threading.Event()
    threading.Timer(0.1, cancel_event.set).start()

    result = run_sqoop_export(
        ssh_cfg(), krb_cfg(), _oracle_cfg(), "DD", "T", "xxx.t", "",
        timeout=3600, cancel_event=cancel_event,
    )

    assert not result.success
    assert "Annulé" in result.error
    assert blocking_channel.closed is True
