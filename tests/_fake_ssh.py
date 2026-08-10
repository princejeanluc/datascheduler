"""
DataScheduler — tests/_fake_ssh.py
Fausses classes paramiko (SSHClient/canal) partagées par tests/test_hadoop_edge.py et
tests/test_spark.py — pas de préfixe test_ : non collecté par pytest, simple module utilitaire.
"""

from core.hadoop_edge import SshExecConfig, KerberosConfig


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


class FakeSSHClient:
    """`exec_fn(cmd, get_pty, timeout) -> (stdin, stdout, stderr)` décide du comportement par
    commande — laisse le test scripter kinit vs. la commande distante vs. le nettoyage.
    `sftp_files` simule le système de fichiers distant vu par open_sftp() (déposer une requête,
    lire un fichier d'erreur via core.hadoop_edge.read_remote_file, rapatrier un résultat)."""

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
        return FakeSftp(self.sftp_files)

    def close(self):
        self.closed = True


def ssh_cfg():
    return SshExecConfig(host="edge01", port=22, username="jdupont", password="pwd")


def krb_cfg():
    return KerberosConfig(principal="jdupont@REALM.EXAMPLE", password="krbpwd")


def install_fake_client(monkeypatch, client: FakeSSHClient):
    import paramiko
    monkeypatch.setattr(paramiko, "SSHClient", lambda: client)
