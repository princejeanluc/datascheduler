"""
DataScheduler — tests/_fake_ssh.py
Fausses classes paramiko (SSHClient/canal) partagées par tests/test_hadoop_edge.py et
tests/test_spark.py — pas de préfixe test_ : non collecté par pytest, simple module utilitaire.
"""

from core.hadoop_edge import SshExecConfig, KerberosConfig, ElevationConfig


class FakeChannel:
    """Simule le canal d'un exec_command() : soit un prompt apparaît (kinit interactif), soit
    la commande se termine directement (kinit échoue avant tout prompt, ou une commande non
    interactive — pas de PTY, donc pas de prompt à attendre)."""

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


class FakeStdin:
    def __init__(self):
        self.written = []

    def write(self, s):
        self.written.append(s)

    def flush(self):
        pass


class FakeStdout:
    def __init__(self, channel, remaining: bytes = b""):
        self.channel = channel
        self._remaining = remaining

    def read(self):
        return self._remaining


class FakeStderr:
    def __init__(self, remaining: bytes = b""):
        self._remaining = remaining

    def read(self):
        return self._remaining


class FakeSftpFile:
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


class FakeSftp:
    def __init__(self, files: dict):
        self._files = files

    def open(self, path, mode="r"):
        return FakeSftpFile(self._files, path, mode)

    def get(self, remote, local):
        from pathlib import Path
        Path(local).write_bytes(self._files.get(remote, b""))

    def close(self):
        pass


class FakeInteractiveChannel:
    """Canal scriptable pour invoke_shell() — utilisé par run_command_with_elevation()
    (core/hadoop_edge.py), qui envoie plusieurs commandes en séquence sur UN SEUL canal
    (contrairement à exec_command(), un process/canal par commande).

    `script_fn(sent_so_far: str) -> str` reçoit tout ce qui a été envoyé au canal jusqu'ici
    (concaténé) et retourne la sortie CUMULÉE disponible en lecture à cet instant — appelée à
    nouveau après chaque send(), donc doit toujours grandir (ou rester stable), jamais rétrécir
    ni "oublier" ce qui était déjà là, comme un vrai transcript de terminal."""

    def __init__(self, script_fn):
        self._script_fn = script_fn
        self._sent = ""
        self._available = script_fn("")   # bannière initiale, avant tout envoi
        self._read_pos = 0

    def send(self, data):
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="replace")
        self._sent += data
        self._available = self._script_fn(self._sent)

    def recv_ready(self):
        return self._read_pos < len(self._available)

    def recv(self, n):
        chunk = self._available[self._read_pos:self._read_pos + n]
        self._read_pos += len(chunk)
        return chunk.encode("utf-8", errors="replace")


class FakeTransport:
    """Simule le Transport d'un client bastion — utilisé par _connect() (core/hadoop_edge.py,
    chantier M) pour ouvrir un canal direct-tcpip vers le saut suivant, exactement comme
    ssh -J. open_channel() n'a pas besoin de retourner un vrai canal exploitable : le fake
    client cible ne s'en sert jamais (connect() l'accepte mais l'ignore, voir FakeSSHClient),
    seul le fait qu'il soit transmis tel quel est vérifié par les tests."""

    def __init__(self):
        self.open_channel_calls = []

    def open_channel(self, kind, dest_addr, src_addr, timeout=None):
        self.open_channel_calls.append((kind, dest_addr, src_addr, timeout))
        return f"<fake-channel to {dest_addr}>"


class FakeSSHClient:
    """`exec_fn(cmd, get_pty, timeout) -> (stdin, stdout, stderr)` décide du comportement par
    commande — laisse le test scripter kinit vs. la commande distante vs. le nettoyage.
    `sftp_files` simule le système de fichiers distant vu par open_sftp() (déposer une requête,
    lire un fichier d'erreur via core.hadoop_edge.read_remote_file, rapatrier un résultat).
    `shell_script_fn`, s'il est fourni, alimente invoke_shell() (voir FakeInteractiveChannel).
    `connect()` accepte et enregistre `sock=` (chantier M, chaînage bastion) sans s'en servir —
    la fausse cible n'a pas besoin d'un vrai tunnel, seul l'objet transmis compte pour les tests."""

    def __init__(self, exec_fn=None, connect_should_fail: bool = False, shell_script_fn=None):
        self._exec_fn = exec_fn
        self._connect_should_fail = connect_should_fail
        self._shell_script_fn = shell_script_fn
        self.closed = False
        self.exec_calls = []
        self.sftp_files: dict = {}
        self.received_sock = "__not_called__"
        self._transport = FakeTransport()

    def set_missing_host_key_policy(self, policy):
        pass

    def connect(self, hostname, port, username, password, timeout, sock=None):
        self.received_sock = sock
        if self._connect_should_fail:
            raise OSError("connexion refusée")

    def exec_command(self, cmd, get_pty=False, timeout=None):
        self.exec_calls.append(cmd)
        return self._exec_fn(cmd, get_pty=get_pty, timeout=timeout)

    def invoke_shell(self):
        return FakeInteractiveChannel(self._shell_script_fn)

    def open_sftp(self):
        return FakeSftp(self.sftp_files)

    def get_transport(self):
        return self._transport

    def close(self):
        self.closed = True


def ssh_cfg(jump_via=None):
    return SshExecConfig(host="edge01", port=22, username="jdupont", password="pwd",
                          jump_via=jump_via)


def krb_cfg():
    return KerberosConfig(principal="jdupont@REALM.EXAMPLE", password="krbpwd")


def elevation_cfg():
    return ElevationConfig(target_user="nifi", password="sharedpw")


def install_fake_client(monkeypatch, client: FakeSSHClient):
    import paramiko
    monkeypatch.setattr(paramiko, "SSHClient", lambda: client)


def install_fake_client_sequence(monkeypatch, clients: list):
    """Pour les tests de chaînage bastion (chantier M) : _connect() appelle paramiko.SSHClient()
    une fois par saut (bastion d'abord — récursion — puis cible), donc un simple monkeypatch qui
    renvoie toujours la même instance ne peut pas représenter deux hôtes distincts. `clients` est
    consommé dans l'ordre d'appel : clients[0] pour le premier saut ouvert (le bastion le plus
    en amont de la chaîne), clients[-1] pour la cible finale."""
    import paramiko
    it = iter(clients)
    monkeypatch.setattr(paramiko, "SSHClient", lambda: next(it))
