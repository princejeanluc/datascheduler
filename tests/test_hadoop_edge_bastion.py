"""
DataScheduler — tests/test_hadoop_edge_bastion.py
Vérifie le chaînage SSH bastion / jump host (chantier M — core/hadoop_edge.py::_connect) : un
profil SSH peut n'être joignable qu'en passant d'abord par un autre profil SSH (edge03
accessible uniquement depuis edge01), technique standard paramiko (canal direct-tcpip sur le
Transport du bastion, utilisé comme sock= pour la connexion cible — équivalent de `ssh -J`).
Aucun cluster réel accessible depuis cet environnement — fausses classes paramiko
(tests/_fake_ssh.py).
"""

import core.hadoop_edge as hadoop_edge
from tests._fake_ssh import (
    FakeSSHClient, ssh_cfg, install_fake_client, install_fake_client_sequence,
)


def _direct_client(connect_should_fail=False):
    return FakeSSHClient(exec_fn=lambda *a, **kw: (None, None, None),
                          connect_should_fail=connect_should_fail)


def test_connect_without_jump_via_behaves_exactly_as_before(monkeypatch):
    """Régression : sock=None transmis, un seul client ouvert/fermé — comportement identique à
    avant le chantier M pour tout profil SSH direct."""
    client = _direct_client()
    install_fake_client(monkeypatch, client)

    c = hadoop_edge._connect(ssh_cfg())
    assert c.received_sock is None
    hadoop_edge._close_all(c)
    assert client.closed is True


def test_connect_chains_through_one_bastion(monkeypatch):
    bastion = _direct_client()
    target = _direct_client()
    install_fake_client_sequence(monkeypatch, [bastion, target])

    cfg = ssh_cfg(jump_via=ssh_cfg())
    cfg.host, cfg.port = "edge03", 22
    cfg.jump_via.host, cfg.jump_via.port = "edge01", 22

    c = hadoop_edge._connect(cfg)
    assert c is target
    # Le canal ouvert par le bastion doit être celui transmis à la connexion cible.
    assert bastion.get_transport().open_channel_calls == [
        ("direct-tcpip", ("edge03", 22), ("localhost", 0), cfg.timeout)
    ]
    assert target.received_sock == "<fake-channel to ('edge03', 22)>"


def test_connect_chains_through_two_bastions(monkeypatch):
    """A -> B -> C : jump_via lui-même a un jump_via — récursion, pas juste 2 sauts."""
    bastion_a = _direct_client()
    bastion_b = _direct_client()
    target_c = _direct_client()
    install_fake_client_sequence(monkeypatch, [bastion_a, bastion_b, target_c])

    cfg_a = ssh_cfg(); cfg_a.host = "A"
    cfg_b = ssh_cfg(jump_via=cfg_a); cfg_b.host = "B"
    cfg_c = ssh_cfg(jump_via=cfg_b); cfg_c.host = "C"

    c = hadoop_edge._connect(cfg_c)
    assert c is target_c
    assert bastion_a.get_transport().open_channel_calls == [
        ("direct-tcpip", ("B", 22), ("localhost", 0), cfg_b.timeout)
    ]
    assert bastion_b.get_transport().open_channel_calls == [
        ("direct-tcpip", ("C", 22), ("localhost", 0), cfg_c.timeout)
    ]


def test_close_all_cascades_through_the_bastion_chain(monkeypatch):
    bastion = _direct_client()
    target = _direct_client()
    install_fake_client_sequence(monkeypatch, [bastion, target])

    c = hadoop_edge._connect(ssh_cfg(jump_via=ssh_cfg()))
    hadoop_edge._close_all(c)
    assert target.closed is True
    assert bastion.closed is True


def test_bastion_unreachable_reports_a_clear_prefixed_message(monkeypatch):
    bastion = _direct_client(connect_should_fail=True)
    install_fake_client_sequence(monkeypatch, [bastion])

    result = hadoop_edge.test_ssh_connection(ssh_cfg(jump_via=ssh_cfg()))
    assert result.success is False
    assert "Bastion" in result.message and "injoignable" in result.message


def test_tunnel_open_channel_failure_reports_a_distinct_message(monkeypatch):
    bastion = _direct_client()

    def _fail_open_channel(kind, dest_addr, src_addr, timeout=None):
        raise OSError("port fermé")
    bastion.get_transport().open_channel = _fail_open_channel

    install_fake_client_sequence(monkeypatch, [bastion])

    result = hadoop_edge.test_ssh_connection(ssh_cfg(jump_via=ssh_cfg()))
    assert result.success is False
    assert "Tunnel" in result.message
    assert bastion.closed is True   # le bastion doit être fermé même si le tunnel échoue


def test_target_unreachable_through_valid_tunnel_reports_a_distinct_message(monkeypatch):
    bastion = _direct_client()
    target = _direct_client(connect_should_fail=True)
    install_fake_client_sequence(monkeypatch, [bastion, target])

    result = hadoop_edge.test_ssh_connection(ssh_cfg(jump_via=ssh_cfg()))
    assert result.success is False
    assert "Bastion" in result.message and "OK" in result.message
    assert bastion.closed is True   # nettoyé même si la connexion finale échoue
