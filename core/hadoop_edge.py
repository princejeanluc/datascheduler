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
import uuid as _uuid_module
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_KINIT_PROMPT_TIMEOUT_S = 15
_SHELL_READ_TIMEOUT_S = 15   # même ordre de grandeur, pour l'invite "sudo su"
_SHELL_BANNER_TIMEOUT_S = 5      # purge de la bannière/prompt initial d'invoke_shell()
_WHOAMI_CONFIRM_TIMEOUT_S = 5    # confirmation d'identité après sudo su


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
class ElevationConfig:
    target_user: str
    password: str


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


def config_from_elevation_profile(profile) -> ElevationConfig:
    from database import crypto
    return ElevationConfig(
        target_user=profile.target_user, password=crypto.decrypt(profile.password),
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
#  ÉLÉVATION DE PRIVILÈGES (sudo su <utilisateur> via canal shell persistant)
# ──────────────────────────────────────────────
# Chaque exec_command() ouvre son propre canal/process côté distant, indépendant des autres —
# un `sudo su` réussi dans l'un ne survit donc JAMAIS à l'exec_command() suivant (la commande
# d'après repart avec l'identité SSH d'origine). Pour préserver le changement d'utilisateur
# entre l'élévation, un kinit optionnel, et la commande réelle, il faut UN SEUL canal shell
# interactif (invoke_shell(), pas exec_command()) sur lequel on envoie les commandes en séquence
# — c'est cette section qui l'implémente, utilisée uniquement quand un profil d'élévation est
# configuré. Le chemin existant (_connect + _kinit optionnel + exec_command par commande, plus
# haut/plus bas dans ce fichier) reste inchangé pour tout le reste — aucun risque de régression
# pour les pipelines qui n'ont pas besoin d'élévation.

def _read_until(channel, markers: list[str], timeout: float) -> tuple[str, str | None]:
    """Lit channel (canal interactif, invoke_shell) jusqu'à ce qu'un des marqueurs apparaisse
    dans le flux cumulé, ou que le délai soit dépassé. Retourne (texte lu, marqueur trouvé ou
    None si délai dépassé). Ne lève jamais."""
    buffer = ""
    start = time.monotonic()
    while True:
        if channel.recv_ready():
            buffer += channel.recv(4096).decode("utf-8", errors="replace")
            for m in markers:
                if m in buffer:
                    return buffer, m
        if time.monotonic() - start > timeout:
            return buffer, None
        time.sleep(0.1)


def run_command_with_elevation(ssh_cfg: SshExecConfig, command: str, timeout: int,
                                elevation_cfg: ElevationConfig,
                                krb_cfg: KerberosConfig | None = None) -> tuple[bool, str]:
    """
    Ouvre UN canal shell interactif (invoke_shell) et y enchaîne, dans l'ordre : `sudo su
    <target_user>` (mot de passe automatisé, même principe que _kinit), une vérification
    d'identité via `whoami` (contrôle positif — on vérifie que le résultat attendu apparaît,
    plutôt que de deviner un message d'erreur précis dont le texte varie selon la configuration
    système), puis un kinit optionnel DANS cette même session (nécessaire si l'utilisateur cible
    a sa propre identité Kerberos), puis la commande réelle avec un marqueur sentinelle unique
    pour capturer sa sortie et son code de sortie sans ambiguïté. Ne lève jamais. Le mot de passe
    n'est jamais journalisé — seulement envoyé sur le canal.

    Limite assumée (même famille que le compromis déjà accepté pour _kinit) : la détection de
    succès/échec de chaque étape intermédiaire repose sur des heuristiques de flux shell (motifs
    dans la sortie brute), pas sur un code de sortie structuré — un prompt shell inhabituel ou un
    message sudo non standard peut faire échouer la détection même si l'élévation a réellement
    réussi (ou l'inverse). Un compromis pragmatique, pas une garantie à 100 %.
    """
    client = _connect(ssh_cfg)
    try:
        channel = client.invoke_shell()
        _read_until(channel, markers=["$", "#"], timeout=_SHELL_BANNER_TIMEOUT_S)

        channel.send(f"sudo su {elevation_cfg.target_user}\n")
        _buf, marker = _read_until(channel, markers=["assword"], timeout=_SHELL_READ_TIMEOUT_S)
        if marker is None:
            return False, "sudo su : délai dépassé en attendant l'invite de mot de passe."
        channel.send(elevation_cfg.password + "\n")

        channel.send("whoami\n")
        _buf, marker = _read_until(channel, markers=[elevation_cfg.target_user], timeout=_WHOAMI_CONFIRM_TIMEOUT_S)
        if marker is None:
            return False, f"sudo su {elevation_cfg.target_user} : échec (identité non confirmée)."

        if krb_cfg:
            channel.send(f"kinit {krb_cfg.principal}\n")
            _buf, marker = _read_until(channel, markers=["assword"], timeout=_KINIT_PROMPT_TIMEOUT_S)
            if marker is None:
                return False, "kinit : délai dépassé en attendant l'invite de mot de passe."
            channel.send(krb_cfg.password + "\n")

        sentinel = f"__DS_DONE_{_uuid_module.uuid4().hex}__"
        channel.send(f"{command} ; echo {sentinel}:$?\n")
        buf, marker = _read_until(channel, markers=[sentinel], timeout=timeout)
        if marker is None:
            return False, f"Délai dépassé ({timeout}s) en attendant la fin de la commande."
        try:
            exit_code = int(buf.split(f"{sentinel}:")[-1].strip().splitlines()[0])
        except (ValueError, IndexError):
            return False, "Impossible de déterminer le code de sortie de la commande."
        return exit_code == 0, buf
    except Exception as e:
        return False, str(e)
    finally:
        client.close()


def test_elevation_auth(ssh_cfg: SshExecConfig, elevation_cfg: ElevationConfig) -> ConnectionTestResult:
    """
    SSH + sudo su <target_user> + vérification d'identité + déconnexion. Ne lève jamais. Pas de
    test d'élévation autonome possible : il faut réellement tenter le sudo su depuis une machine
    — d'où la dépendance à un profil SSH pour ce test, comme pour Kerberos.
    """
    success, message = run_command_with_elevation(
        ssh_cfg, "true", timeout=10, elevation_cfg=elevation_cfg,
    )
    if success:
        return ConnectionTestResult(True, f"Élévation vers « {elevation_cfg.target_user} » réussie.")
    return ConnectionTestResult(False, message)


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
