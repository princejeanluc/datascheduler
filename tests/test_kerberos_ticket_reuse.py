"""
DataScheduler — tests/test_kerberos_ticket_reuse.py
Réutilisation des tickets Kerberos (chantier dédié) : un ticket kinit dure ~24h, mais jusqu'ici
kinit était relancé sans condition à chaque étape SPARK_SQL/SQOOP_EXPORT/SQOOP_IMPORT — signalé
par un utilisateur, confirmé par investigation du code (zéro `klist` nulle part). Corrigé via
deux réglages AppSettings (kerberos_reuse_valid_ticket, kerberos_ticket_grace_period_s) — voir
CHANGELOG pour la nuance sur l'accumulation réelle de tickets vs. appels kinit redondants.

Toute défaillance de détection (klist absent, sortie inattendue, timeout) doit retomber sur
False/"aucun ticket valide" — jamais pire que le comportement historique (kinit systématique).
"""

import re

import core.hadoop_edge as hadoop_edge
from database import db_manager as db
from tests._fake_ssh import (
    FakeChannel, FakeStdin, FakeStdout, FakeStderr, FakeSSHClient, FakeInteractiveChannel,
    ssh_cfg, krb_cfg, elevation_cfg, install_fake_client,
)


# ──────────────────────────────────────────────
#  AppSettings — défauts et persistance
# ──────────────────────────────────────────────

def test_new_app_settings_row_defaults_to_reuse_enabled_with_no_grace(test_db):
    """Défaut = True/0, mais pas pour "préserver" un comportement historique (il n'y en avait
    pas) : le nouveau chemin ne peut jamais être pire que l'ancien, voir CHANGELOG."""
    settings = db.get_app_settings()
    assert settings.kerberos_reuse_valid_ticket is True
    assert settings.kerberos_ticket_grace_period_s == 0


def test_app_settings_kerberos_fields_round_trip(test_db):
    db.update_app_settings(kerberos_reuse_valid_ticket=False, kerberos_ticket_grace_period_s=300)
    settings = db.get_app_settings()
    assert settings.kerberos_reuse_valid_ticket is False
    assert settings.kerberos_ticket_grace_period_s == 300


# ──────────────────────────────────────────────
#  _has_valid_ticket() — klist -s, exec_command
# ──────────────────────────────────────────────

def test_has_valid_ticket_true_when_klist_exits_zero():
    def exec_fn(cmd, get_pty=False, timeout=None):
        return FakeStdin(), FakeStdout(FakeChannel(exit_status=0)), FakeStderr()
    client = FakeSSHClient(exec_fn)
    assert hadoop_edge._has_valid_ticket(client) is True


def test_has_valid_ticket_false_when_klist_exits_nonzero():
    def exec_fn(cmd, get_pty=False, timeout=None):
        return FakeStdin(), FakeStdout(FakeChannel(exit_status=1)), FakeStderr()
    client = FakeSSHClient(exec_fn)
    assert hadoop_edge._has_valid_ticket(client) is False


def test_has_valid_ticket_false_when_exec_command_raises():
    def exec_fn(cmd, get_pty=False, timeout=None):
        raise OSError("klist: command not found")
    client = FakeSSHClient(exec_fn)
    assert hadoop_edge._has_valid_ticket(client) is False


# ──────────────────────────────────────────────
#  _ticket_remaining_seconds() — klist + awk + date -d, exec_command
# ──────────────────────────────────────────────

def test_ticket_remaining_seconds_parses_positive_output():
    def exec_fn(cmd, get_pty=False, timeout=None):
        return FakeStdin(), FakeStdout(FakeChannel(exit_status=0), remaining=b"3600\n"), FakeStderr()
    client = FakeSSHClient(exec_fn)
    assert hadoop_edge._ticket_remaining_seconds(client) == 3600


def test_ticket_remaining_seconds_returns_minus_one_on_unparseable_output():
    def exec_fn(cmd, get_pty=False, timeout=None):
        return FakeStdin(), FakeStdout(FakeChannel(exit_status=0), remaining=b"garbage"), FakeStderr()
    client = FakeSSHClient(exec_fn)
    assert hadoop_edge._ticket_remaining_seconds(client) == -1


def test_ticket_remaining_seconds_returns_minus_one_when_exec_command_raises():
    def exec_fn(cmd, get_pty=False, timeout=None):
        raise OSError("boom")
    client = FakeSSHClient(exec_fn)
    assert hadoop_edge._ticket_remaining_seconds(client) == -1


# ──────────────────────────────────────────────
#  _should_skip_kinit() — choix du chemin selon grace_period_s
# ──────────────────────────────────────────────

def test_should_skip_kinit_uses_has_valid_ticket_when_grace_is_zero(monkeypatch):
    calls = []
    monkeypatch.setattr(hadoop_edge, "_has_valid_ticket", lambda client: calls.append("simple") or True)
    monkeypatch.setattr(hadoop_edge, "_ticket_remaining_seconds", lambda client: calls.append("precise") or 0)
    assert hadoop_edge._should_skip_kinit(object(), 0) is True
    assert calls == ["simple"]


def test_should_skip_kinit_uses_remaining_seconds_when_grace_is_positive(monkeypatch):
    calls = []
    monkeypatch.setattr(hadoop_edge, "_has_valid_ticket", lambda client: calls.append("simple") or True)
    monkeypatch.setattr(hadoop_edge, "_ticket_remaining_seconds", lambda client: calls.append("precise") or 500)
    assert hadoop_edge._should_skip_kinit(object(), 300) is True
    assert calls == ["precise"]


def test_should_skip_kinit_false_when_remaining_time_below_grace(monkeypatch):
    monkeypatch.setattr(hadoop_edge, "_ticket_remaining_seconds", lambda client: 100)
    assert hadoop_edge._should_skip_kinit(object(), 300) is False


# ──────────────────────────────────────────────
#  _kinit() — intégration avec reuse_ticket/grace_period_s
# ──────────────────────────────────────────────

def test_kinit_skips_entirely_when_a_valid_ticket_already_exists(monkeypatch):
    monkeypatch.setattr(hadoop_edge, "_should_skip_kinit", lambda client, grace: True)

    def exec_fn(cmd, get_pty=False, timeout=None):
        raise AssertionError("kinit ne doit jamais être appelé quand un ticket valide existe")

    client = FakeSSHClient(exec_fn)
    ok, message = hadoop_edge._kinit(client, krb_cfg(), reuse_ticket=True, grace_period_s=0)
    assert ok is True
    assert "réutilisé" in message


def test_kinit_runs_normally_when_reuse_ticket_is_false_the_default():
    """Défaut de la fonction (False) délibérément différent du défaut applicatif (True) — voir
    docstring de _kinit(). Comportement historique inchangé pour tout appelant qui ne le
    transmet pas explicitement."""
    def exec_fn(cmd, get_pty=False, timeout=None):
        channel = FakeChannel(prompt_bytes=b"Password: ", exit_status=0, has_prompt=True)
        return FakeStdin(), FakeStdout(channel), FakeStderr()

    client = FakeSSHClient(exec_fn)
    ok, message = hadoop_edge._kinit(client, krb_cfg())
    assert ok is True
    assert "réussi" in message
    assert client.exec_calls   # kinit a bien été appelé


def test_kinit_runs_normally_when_reuse_ticket_true_but_no_valid_ticket(monkeypatch):
    monkeypatch.setattr(hadoop_edge, "_should_skip_kinit", lambda client, grace: False)

    def exec_fn(cmd, get_pty=False, timeout=None):
        channel = FakeChannel(prompt_bytes=b"Password: ", exit_status=0, has_prompt=True)
        return FakeStdin(), FakeStdout(channel), FakeStderr()

    client = FakeSSHClient(exec_fn)
    ok, message = hadoop_edge._kinit(client, krb_cfg(), reuse_ticket=True, grace_period_s=0)
    assert ok is True
    assert "réussi" in message


# ──────────────────────────────────────────────
#  _shell_should_skip_kinit() — équivalent pour un canal shell interactif (élévation)
# ──────────────────────────────────────────────

def test_shell_should_skip_kinit_grace_zero_true_on_zero_exit_code():
    def script_fn(sent: str) -> str:
        m = re.search(r"echo (__DS_KLIST_\w+__):\$\?", sent)
        return f"{m.group(1)}:0\n" if m else ""

    channel = FakeInteractiveChannel(script_fn)
    assert hadoop_edge._shell_should_skip_kinit(channel, 0) is True


def test_shell_should_skip_kinit_grace_zero_false_on_nonzero_exit_code():
    def script_fn(sent: str) -> str:
        m = re.search(r"echo (__DS_KLIST_\w+__):\$\?", sent)
        return f"{m.group(1)}:1\n" if m else ""

    channel = FakeInteractiveChannel(script_fn)
    assert hadoop_edge._shell_should_skip_kinit(channel, 0) is False


def test_shell_should_skip_kinit_grace_positive_compares_remaining_seconds():
    def script_fn(sent: str) -> str:
        m = re.search(r"echo (__DS_KLIST_\w+__):\$R", sent)
        return f"{m.group(1)}:500\n" if m else ""

    assert hadoop_edge._shell_should_skip_kinit(FakeInteractiveChannel(script_fn), 300) is True
    assert hadoop_edge._shell_should_skip_kinit(FakeInteractiveChannel(script_fn), 600) is False


def test_shell_should_skip_kinit_false_when_marker_never_appears(monkeypatch):
    monkeypatch.setattr(hadoop_edge, "_WHOAMI_CONFIRM_TIMEOUT_S", 0.2)
    channel = FakeInteractiveChannel(lambda sent: "")
    assert hadoop_edge._shell_should_skip_kinit(channel, 0) is False


# ──────────────────────────────────────────────
#  run_command_with_elevation() — intégration (chemin élévation)
# ──────────────────────────────────────────────

def _success_script(target_user="nifi", with_kinit=False, krb_principal=None, command_exit_code=0):
    """Copie locale de tests/test_hadoop_edge_elevation.py::_success_script() — un import direct
    créerait un couplage entre deux fichiers de test sans rapport fonctionnel autrement."""
    def script_fn(sent: str) -> str:
        out = "user@edge03:~$ "
        su_cmd = f"sudo su {target_user}\n"
        if su_cmd not in sent:
            return out
        out += su_cmd + "[sudo] password for user: "
        after_su = sent.split(su_cmd, 1)[-1]
        if "\n" not in after_su:
            return out
        out += f"\n{target_user}@edge03:~$ "
        if "whoami" not in sent:
            return out
        out += f"whoami\n{target_user}\n{target_user}@edge03:~$ "

        if with_kinit:
            kinit_cmd = f"kinit {krb_principal}\n"
            if kinit_cmd not in sent:
                return out
            out += f"kinit {krb_principal}\nPassword for {krb_principal}: "
            after_kinit = sent.split(kinit_cmd, 1)[-1]
            if "\n" not in after_kinit:
                return out
            out += f"\n{target_user}@edge03:~$ "

        m_sentinel = re.search(r"; echo (__DS_DONE_\w+__):\$\?", sent)
        if not m_sentinel:
            return out
        sentinel = m_sentinel.group(1)
        out += f"{sentinel}:{command_exit_code}\n{target_user}@edge03:~$ "
        return out
    return script_fn


def test_elevation_path_skips_kinit_when_reuse_ticket_and_valid_ticket_exists(monkeypatch):
    krb = krb_cfg()
    monkeypatch.setattr(hadoop_edge, "_shell_should_skip_kinit",
                         lambda channel, grace, cancel_event=None: True)
    sent_log = []
    base_script = _success_script()   # ne gère jamais de branche kinit
    def script_fn(sent):
        sent_log.append(sent)
        return base_script(sent)
    client = FakeSSHClient(shell_script_fn=script_fn)
    install_fake_client(monkeypatch, client)

    ok, output = hadoop_edge.run_command_with_elevation(
        ssh_cfg(), "sqoop export ...", timeout=10, elevation_cfg=elevation_cfg(), krb_cfg=krb,
        reuse_ticket=True, grace_period_s=0,
    )

    assert ok, output
    assert f"kinit {krb.principal}" not in (sent_log[-1] if sent_log else "")


def test_elevation_path_still_runs_kinit_when_reuse_ticket_true_but_no_valid_ticket(monkeypatch):
    krb = krb_cfg()
    monkeypatch.setattr(hadoop_edge, "_shell_should_skip_kinit",
                         lambda channel, grace, cancel_event=None: False)
    client = FakeSSHClient(shell_script_fn=_success_script(with_kinit=True, krb_principal=krb.principal))
    install_fake_client(monkeypatch, client)

    ok, output = hadoop_edge.run_command_with_elevation(
        ssh_cfg(), "sqoop export ...", timeout=10, elevation_cfg=elevation_cfg(), krb_cfg=krb,
        reuse_ticket=True, grace_period_s=0,
    )

    assert ok, output


def test_elevation_path_runs_kinit_normally_when_reuse_ticket_false_the_default(monkeypatch):
    """Comportement historique inchangé pour tout appelant qui ne transmet pas explicitement
    reuse_ticket (core/sqoop.py le fait toujours désormais, mais la fonction de bas niveau reste
    sûre par défaut)."""
    krb = krb_cfg()
    client = FakeSSHClient(shell_script_fn=_success_script(with_kinit=True, krb_principal=krb.principal))
    install_fake_client(monkeypatch, client)

    ok, output = hadoop_edge.run_command_with_elevation(
        ssh_cfg(), "sqoop export ...", timeout=10, elevation_cfg=elevation_cfg(), krb_cfg=krb,
    )
    assert ok, output
