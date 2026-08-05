"""
DataScheduler — core/spark.py
Exécution de requêtes Spark SQL sur un cluster Hadoop via un nœud edge : connexion SSH,
authentification Kerberos (kinit, automatisé via un pseudo-terminal — les comptes sont
nominatifs, pas de compte de service avec keytab possible, donc kinit reste interactif),
exécution non-interactive de spark-sql, rapatriement optionnel du résultat par SFTP.

Aucune vérification de clé d'hôte SSH (AutoAddPolicy) — même politique que core/ftp.py, qui ne
vérifie pas non plus les clés d'hôte pour SFTP : cohérent avec l'absence de convention stricte
déjà établie dans ce projet, pas une régression.
"""

import logging
import time
import uuid as _uuid_module
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_KINIT_PROMPT_TIMEOUT_S = 15


# ──────────────────────────────────────────────
#  DATACLASSES DE CONFIGURATION / RÉSULTATS
# ──────────────────────────────────────────────

@dataclass
class SshExecConfig:
    host: str
    port: int
    username: str
    password: str
    timeout: int = 30


@dataclass
class KerberosConfig:
    principal: str
    password: str


@dataclass
class ConnectionTestResult:
    success: bool
    message: str


@dataclass
class SparkSqlResult:
    success: bool
    error: str = ""
    local_output_path: Path | None = None
    duration_s: float = 0.0


def config_from_profile(profile) -> SshExecConfig:
    from database import crypto
    return SshExecConfig(
        host=profile.host, port=profile.port, username=profile.username,
        password=crypto.decrypt(profile.password),
    )


def kerberos_config_from_profile(profile) -> KerberosConfig:
    from database import crypto
    return KerberosConfig(
        principal=profile.principal, password=crypto.decrypt(profile.password),
    )


# ──────────────────────────────────────────────
#  CONNEXION SSH
# ──────────────────────────────────────────────

def _connect(cfg: SshExecConfig):
    import paramiko
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=cfg.host, port=cfg.port, username=cfg.username, password=cfg.password,
        timeout=cfg.timeout,
    )
    return client


def test_ssh_connection(cfg: SshExecConfig) -> ConnectionTestResult:
    """Connexion SSH puis déconnexion immédiate. Ne lève jamais."""
    client = None
    try:
        client = _connect(cfg)
        return ConnectionTestResult(True, "Connexion SSH réussie.")
    except Exception as e:
        return ConnectionTestResult(False, str(e))
    finally:
        if client is not None:
            client.close()


# ──────────────────────────────────────────────
#  KERBEROS (kinit via pseudo-terminal)
# ──────────────────────────────────────────────

def _kinit(client, krb_cfg: KerberosConfig) -> tuple[bool, str]:
    """
    Automatise le prompt interactif de `kinit` via un pseudo-terminal (get_pty=True) — kinit
    lit le mot de passe depuis le terminal contrôlant, pas depuis stdin brut (mesure
    anti-script délibérée de Kerberos), donc `echo motdepasse | kinit ...` ne fonctionne pas ;
    un PTY fait croire à kinit qu'il parle à un vrai terminal. Ne lève jamais.
    """
    stdin, stdout, stderr = client.exec_command(
        f"kinit {krb_cfg.principal}", get_pty=True, timeout=30,
    )
    channel = stdout.channel
    buffer = ""
    start = time.monotonic()
    while "assword" not in buffer:
        if channel.recv_ready():
            buffer += channel.recv(4096).decode("utf-8", errors="replace")
            continue
        if channel.exit_status_ready():
            break
        if time.monotonic() - start > _KINIT_PROMPT_TIMEOUT_S:
            return False, "kinit : délai dépassé en attendant l'invite de mot de passe."
        time.sleep(0.1)

    stdin.write(krb_cfg.password + "\n")
    stdin.flush()
    exit_status = channel.recv_exit_status()
    remaining = (
        stdout.read().decode("utf-8", errors="replace")
        + stderr.read().decode("utf-8", errors="replace")
    )

    if exit_status == 0:
        return True, "kinit réussi."
    return False, remaining.strip() or f"kinit a échoué (code {exit_status})."


def test_kerberos_auth(ssh_cfg: SshExecConfig, krb_cfg: KerberosConfig) -> ConnectionTestResult:
    """
    SSH + kinit + déconnexion. Ne lève jamais. Pas de test Kerberos autonome possible : un
    ticket ne s'obtient qu'en lançant réellement kinit depuis une machine — d'où la dépendance
    à un profil SSH pour ce test, contrairement aux autres profils de l'app.
    """
    client = None
    try:
        client = _connect(ssh_cfg)
        success, message = _kinit(client, krb_cfg)
        return ConnectionTestResult(success, message)
    except Exception as e:
        return ConnectionTestResult(False, str(e))
    finally:
        if client is not None:
            client.close()


# ──────────────────────────────────────────────
#  EXÉCUTION SPARK SQL
# ──────────────────────────────────────────────

def _read_remote_file(client, remote_path: str, max_bytes: int = 4000) -> str:
    """Lecture best-effort d'un petit fichier distant (message d'erreur) — ne lève jamais."""
    try:
        sftp = client.open_sftp()
        try:
            with sftp.open(remote_path, "r") as f:
                return f.read(max_bytes).decode("utf-8", errors="replace")
        finally:
            sftp.close()
    except Exception:
        return "(détail indisponible)"


def run_spark_sql(ssh_cfg: SshExecConfig, krb_cfg: KerberosConfig, spark_conf: str, query: str,
                   fetch_result: bool, local_output_path: Path | None = None,
                   timeout: int = 3600) -> SparkSqlResult:
    """
    SSH → kinit → dépose la requête dans un fichier .sql temporaire distant (SFTP — évite tout
    problème d'échappement shell d'une requête inline) → exécute spark-sql non-interactivement,
    sortie redirigée vers un fichier distant, borné par `timeout` (le utilitaire shell, pas
    seulement le paramètre côté client — exec_command() ne borne pas la durée du process
    distant lui-même) → si fetch_result, rapatrie ce fichier par SFTP → nettoie les fichiers
    temporaires distants (best-effort, jamais bloquant) → ferme toujours la connexion SSH
    (finally), même principe que le try/finally déjà appliqué aux steps DB_EXTRACT/DB_EXECUTE/
    DB_LOAD (core/steps/*.py).
    """
    start = time.monotonic()
    client = None
    token = _uuid_module.uuid4().hex
    remote_sql = f"/tmp/ds_spark_{token}.sql"
    remote_out = f"/tmp/ds_spark_{token}.out"
    remote_err = f"/tmp/ds_spark_{token}.err"

    try:
        client = _connect(ssh_cfg)

        ok, message = _kinit(client, krb_cfg)
        if not ok:
            return SparkSqlResult(
                success=False, error=f"Authentification Kerberos : {message}",
                duration_s=time.monotonic() - start,
            )

        sftp = client.open_sftp()
        try:
            with sftp.open(remote_sql, "w") as f:
                f.write(query)
        finally:
            sftp.close()

        cmd = (
            f"timeout {int(timeout)}s spark-sql -S {spark_conf} "
            f"-f {remote_sql} > {remote_out} 2>{remote_err}"
        )
        _stdin, stdout, _stderr = client.exec_command(cmd, timeout=timeout + 30)
        exit_status = stdout.channel.recv_exit_status()

        if exit_status != 0:
            err_text = _read_remote_file(client, remote_err)
            return SparkSqlResult(
                success=False, error=f"spark-sql a échoué (code {exit_status}) : {err_text}",
                duration_s=time.monotonic() - start,
            )

        if fetch_result and local_output_path is not None:
            sftp = client.open_sftp()
            try:
                sftp.get(remote_out, str(local_output_path))
            finally:
                sftp.close()

        return SparkSqlResult(
            success=True,
            local_output_path=local_output_path if fetch_result else None,
            duration_s=time.monotonic() - start,
        )

    except Exception as e:
        return SparkSqlResult(success=False, error=str(e), duration_s=time.monotonic() - start)
    finally:
        if client is not None:
            try:
                client.exec_command(f"rm -f {remote_sql} {remote_out} {remote_err}")
            except Exception:
                pass
            client.close()
