"""
DataScheduler — core/hadoop_edge.py
Connexion SSH à un nœud edge d'un cluster Hadoop + authentification Kerberos (kinit) —
mécanique commune à toute étape qui exécute une commande sur ce cluster (SPARK_SQL,
SQOOP_EXPORT), extraite de core/spark.py (chantier K) pour ne pas dupliquer la logique kinit
par pseudo-terminal (comptes nominatifs, pas de compte de service avec keytab possible, donc
kinit reste interactif — délicate : timeout d'invite, lecture du prompt caractère par caractère).

Aucune vérification de clé d'hôte SSH (AutoAddPolicy) — même politique que core/ftp.py, qui ne
vérifie pas non plus les clés d'hôte pour SFTP : cohérent avec l'absence de convention stricte
déjà établie dans ce projet, pas une régression.
"""

import logging
import time
from dataclasses import dataclass

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
#  UTILITAIRE PARTAGÉ — LECTURE D'UN FICHIER DISTANT
# ──────────────────────────────────────────────

def read_remote_file(client, remote_path: str, max_bytes: int = 4000) -> str:
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
