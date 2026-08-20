"""
DataScheduler — tests/test_hadoop_edge_elevation.py
Vérifie core.hadoop_edge.run_command_with_elevation()/test_elevation_auth() (chantier L) : les
commandes s'enchaînent sur UN SEUL canal shell interactif (invoke_shell), contrairement à
exec_command() qui isole chaque commande dans son propre process — voir la docstring du module.
Couvre : succès (sudo su + whoami confirmé + commande + sentinel), délai dépassé sur le prompt
sudo, identité non confirmée après sudo, kinit optionnel enchaîné dans la même session, absence
du mot de passe dans la valeur de retour en cas d'échec.
"""

import re
import threading

import core.hadoop_edge as hadoop_edge
from tests._fake_ssh import FakeSSHClient, ssh_cfg, krb_cfg, elevation_cfg, install_fake_client


def _success_script(target_user="nifi", with_kinit=False, krb_principal=None,
                     command_exit_code=0):
    """Construit un script_fn simulant un `sudo su <target_user>` réussi, une confirmation
    `whoami`, un `kinit` optionnel réussi, puis la commande réelle avec son marqueur sentinelle
    reflété avec le code de sortie demandé."""
    def script_fn(sent: str) -> str:
        out = f"user@edge03:~$ "
        su_cmd = f"sudo su {target_user}\n"
        if su_cmd not in sent:
            return out
        out += su_cmd + "[sudo] password for user: "
        # Le mot de passe sudo est la ligne envoyée après la commande sudo su elle-même.
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
            # Le mot de passe kinit est la ligne envoyée après la commande kinit elle-même.
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


def test_run_command_with_elevation_success_without_kinit(monkeypatch):
    client = FakeSSHClient(shell_script_fn=_success_script())
    install_fake_client(monkeypatch, client)

    ok, output = hadoop_edge.run_command_with_elevation(
        ssh_cfg(), "sqoop export ...", timeout=10, elevation_cfg=elevation_cfg(),
    )

    assert ok, output
    assert client.closed is True


def test_run_command_with_elevation_success_with_kinit_chained(monkeypatch):
    krb = krb_cfg()
    client = FakeSSHClient(shell_script_fn=_success_script(with_kinit=True, krb_principal=krb.principal))
    install_fake_client(monkeypatch, client)

    ok, output = hadoop_edge.run_command_with_elevation(
        ssh_cfg(), "sqoop export ...", timeout=10, elevation_cfg=elevation_cfg(), krb_cfg=krb,
    )

    assert ok, output


def test_run_command_with_elevation_reports_nonzero_exit_code(monkeypatch):
    client = FakeSSHClient(shell_script_fn=_success_script(command_exit_code=1))
    install_fake_client(monkeypatch, client)

    ok, output = hadoop_edge.run_command_with_elevation(
        ssh_cfg(), "sqoop export ...", timeout=10, elevation_cfg=elevation_cfg(),
    )

    assert not ok


def test_run_command_with_elevation_times_out_on_sudo_prompt(monkeypatch):
    monkeypatch.setattr(hadoop_edge, "_SHELL_READ_TIMEOUT_S", 0.2)

    def stuck_script(sent: str) -> str:
        return "user@edge03:~$ "   # ne montre jamais d'invite de mot de passe

    client = FakeSSHClient(shell_script_fn=stuck_script)
    install_fake_client(monkeypatch, client)

    ok, output = hadoop_edge.run_command_with_elevation(
        ssh_cfg(), "sqoop export ...", timeout=10, elevation_cfg=elevation_cfg(),
    )

    assert not ok
    assert "délai dépassé" in output


def test_run_command_with_elevation_fails_when_identity_not_confirmed(monkeypatch):
    monkeypatch.setattr(hadoop_edge, "_WHOAMI_CONFIRM_TIMEOUT_S", 0.2)

    def wrong_identity_script(sent: str) -> str:
        out = "user@edge03:~$ "
        if "sudo su" not in sent:
            return out
        out += "sudo su nifi\n[sudo] password for user: \nuser@edge03:~$ "   # sudo a échoué, même prompt qu'avant
        if "whoami" in sent:
            out += "whoami\nuser\nuser@edge03:~$ "   # toujours "user", pas "nifi"
        return out

    client = FakeSSHClient(shell_script_fn=wrong_identity_script)
    install_fake_client(monkeypatch, client)

    ok, output = hadoop_edge.run_command_with_elevation(
        ssh_cfg(), "sqoop export ...", timeout=5, elevation_cfg=elevation_cfg(),
    )

    assert not ok
    assert "identité non confirmée" in output


def test_run_command_with_elevation_never_leaks_password_on_failure(monkeypatch):
    def stuck_script(sent: str) -> str:
        return "user@edge03:~$ "

    monkeypatch.setattr(hadoop_edge, "_SHELL_READ_TIMEOUT_S", 0.2)
    client = FakeSSHClient(shell_script_fn=stuck_script)
    install_fake_client(monkeypatch, client)

    ok, output = hadoop_edge.run_command_with_elevation(
        ssh_cfg(), "sqoop export ...", timeout=10, elevation_cfg=elevation_cfg(),
    )

    assert not ok
    assert "sharedpw" not in output


def test_run_command_with_elevation_reports_phase_ticks_without_kinit(monkeypatch):
    """chantier O : on_progress reflète chaque phase franchie (pas de progression continue
    pendant l'attente elle-même) — notamment le dernier tick, "Exécution de la commande…",
    émis juste avant l'attente potentiellement la plus longue."""
    client = FakeSSHClient(shell_script_fn=_success_script())
    install_fake_client(monkeypatch, client)
    ticks = []

    ok, _ = hadoop_edge.run_command_with_elevation(
        ssh_cfg(), "sqoop export ...", timeout=10, elevation_cfg=elevation_cfg(),
        on_progress=lambda msg, pct: ticks.append((msg, pct)),
    )

    assert ok
    messages = [m for m, _ in ticks]
    assert messages == [
        "Connexion au nœud edge…",
        "Élévation vers « nifi »…",
        "Exécution de la commande…",
    ]
    pcts = [p for _, p in ticks]
    assert pcts == sorted(pcts)   # strictement croissant


def test_run_command_with_elevation_reports_kerberos_tick_when_configured(monkeypatch):
    krb = krb_cfg()
    client = FakeSSHClient(shell_script_fn=_success_script(with_kinit=True, krb_principal=krb.principal))
    install_fake_client(monkeypatch, client)
    ticks = []

    hadoop_edge.run_command_with_elevation(
        ssh_cfg(), "sqoop export ...", timeout=10, elevation_cfg=elevation_cfg(), krb_cfg=krb,
        on_progress=lambda msg, pct: ticks.append((msg, pct)),
    )

    messages = [m for m, _ in ticks]
    assert messages == [
        "Connexion au nœud edge…",
        "Élévation vers « nifi »…",
        "Authentification Kerberos…",
        "Exécution de la commande…",
    ]


def test_run_command_with_elevation_without_on_progress_still_works(monkeypatch):
    """on_progress=None (défaut) ne doit jamais lever — comportement inchangé pour tout
    appelant qui ne fournit pas ce paramètre."""
    client = FakeSSHClient(shell_script_fn=_success_script())
    install_fake_client(monkeypatch, client)

    ok, output = hadoop_edge.run_command_with_elevation(
        ssh_cfg(), "sqoop export ...", timeout=10, elevation_cfg=elevation_cfg(),
    )
    assert ok, output


def test_test_elevation_auth_reports_success(monkeypatch):
    client = FakeSSHClient(shell_script_fn=_success_script())
    install_fake_client(monkeypatch, client)

    result = hadoop_edge.test_elevation_auth(ssh_cfg(), elevation_cfg())

    assert result.success is True
    assert "nifi" in result.message


def test_run_command_with_elevation_returns_cancelled_message_instead_of_timeout(monkeypatch):
    """sudo su/whoami se résolvent normalement (script scripté pour y répondre), mais la
    commande réelle ne produit jamais son marqueur sentinelle — simule une commande distante
    toujours en cours au moment où l'utilisateur annule. cancel_event est positionné par un
    timer, une fois l'élévation déjà passée, pour vérifier que c'est bien l'attente de la
    commande (la phase la plus longue) qui est interrompue, pas une étape antérieure."""
    def stuck_after_login_script(sent: str) -> str:
        out = "user@edge03:~$ "
        su_cmd = "sudo su nifi\n"
        if su_cmd not in sent:
            return out
        out += su_cmd + "[sudo] password for user: "
        after_su = sent.split(su_cmd, 1)[-1]
        if "\n" not in after_su:
            return out
        out += "\nnifi@edge03:~$ "
        if "whoami" not in sent:
            return out
        out += "whoami\nnifi\nnifi@edge03:~$ "
        return out   # jamais de marqueur sentinelle, quoi qu'il soit envoyé ensuite

    client = FakeSSHClient(shell_script_fn=stuck_after_login_script)
    install_fake_client(monkeypatch, client)
    cancel_event = threading.Event()
    threading.Timer(0.05, cancel_event.set).start()

    ok, output = hadoop_edge.run_command_with_elevation(
        ssh_cfg(), "sqoop export ...", timeout=3600, elevation_cfg=elevation_cfg(),
        cancel_event=cancel_event,
    )

    assert not ok
    assert "Annulé" in output


def test_test_elevation_auth_reports_failure_without_raising(monkeypatch):
    monkeypatch.setattr(hadoop_edge, "_SHELL_READ_TIMEOUT_S", 0.2)

    def stuck_script(sent: str) -> str:
        return "user@edge03:~$ "

    client = FakeSSHClient(shell_script_fn=stuck_script)
    install_fake_client(monkeypatch, client)

    result = hadoop_edge.test_elevation_auth(ssh_cfg(), elevation_cfg())

    assert result.success is False
