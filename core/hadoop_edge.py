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
    # Bastion optionnel (chantier M) : si renseigné, _connect() se connecte d'abord à jump_via
    # puis ouvre un tunnel direct-tcpip depuis son canal vers (host, port) — équivalent de
    # `ssh -J`. Récursif : jump_via peut lui-même avoir un jump_via, chaîne de longueur arbitraire.
    jump_via: "SshExecConfig | None" = None


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
    """Résout aussi la chaîne de bastions (jump_via_id, chantier M) récursivement, via de
    nouvelles requêtes explicites plutôt qu'une relationship ORM — voir la note dans
    database/models.py::SshProfile sur pourquoi (DetachedInstanceError)."""
    from database import crypto, db_manager as db
    jump = None
    if profile.jump_via_id:
        jump_profile = db.get_ssh_profile(profile.jump_via_id)
        if jump_profile:
            jump = config_from_profile(jump_profile)
    return SshExecConfig(
        host=profile.host, port=profile.port, username=profile.username,
        password=crypto.decrypt(profile.password), jump_via=jump,
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
    """
    Connexion SSH directe, ou en chaîne via un ou plusieurs bastions (cfg.jump_via, chantier M) :
    technique standard paramiko pour un jump host (équivalent de `ssh -J`) — se connecter d'abord
    au bastion, ouvrir un canal `direct-tcpip` sur son Transport vers (host, port), l'utiliser
    comme `sock=` pour la connexion cible (le tunnel tient lieu de socket TCP). Récursif : chaque
    bastion peut lui-même en avoir un. Sans jump_via, comportement strictement identique à avant
    (sock=None) — aucun risque de régression pour un profil SSH direct.

    Trois échecs distincts et clairement préfixés (utile pour savoir lequel des sauts pose
    problème depuis le résultat d'un test de connexion) : bastion injoignable, tunnel impossible
    (bastion joint mais route fermée vers la cible), cible injoignable via un tunnel pourtant
    valide (bastion + tunnel OK, mais échec SSH sur la cible elle-même).
    """
    import paramiko
    sock = None
    bastion_client = None
    if cfg.jump_via:
        try:
            bastion_client = _connect(cfg.jump_via)
        except Exception as e:
            raise ConnectionError(
                f"Bastion {cfg.jump_via.host}:{cfg.jump_via.port} injoignable : {e}"
            ) from e
        try:
            sock = bastion_client.get_transport().open_channel(
                "direct-tcpip", (cfg.host, cfg.port), ("localhost", 0), timeout=cfg.timeout,
            )
        except Exception as e:
            _close_all(bastion_client)
            raise ConnectionError(
                f"Tunnel vers {cfg.host}:{cfg.port} via le bastion {cfg.jump_via.host} "
                f"impossible : {e}"
            ) from e

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=cfg.host, port=cfg.port, username=cfg.username, password=cfg.password,
            timeout=cfg.timeout, sock=sock,
        )
    except Exception as e:
        if bastion_client is not None:
            _close_all(bastion_client)
            raise ConnectionError(
                f"Bastion {cfg.jump_via.host} OK, mais connexion à {cfg.host}:{cfg.port} "
                f"via le tunnel a échoué : {e}"
            ) from e
        raise
    if bastion_client is not None:
        client._ds_bastion_chain = [bastion_client]
    return client


def _close_all(client) -> None:
    """Ferme client puis, en cascade, tout bastion intermédiaire ouvert pour l'atteindre (voir
    _connect) — sans quoi une session SSH sur le bastion resterait ouverte indéfiniment (fuite de
    connexion, visible côté audit/logs du bastion). Sans jump_via, se comporte exactement comme
    client.close() d'avant — aucun changement de comportement pour les profils directs."""
    try:
        client.close()
    finally:
        for bastion in getattr(client, "_ds_bastion_chain", []):
            _close_all(bastion)


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
            _close_all(client)


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
            _close_all(client)


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
                                krb_cfg: KerberosConfig | None = None,
                                on_progress=None) -> tuple[bool, str]:
    """
    Ouvre UN canal shell interactif (invoke_shell) et y enchaîne, dans l'ordre : `sudo su
    <target_user>` (mot de passe automatisé, même principe que _kinit), une vérification
    d'identité via `whoami` (contrôle positif — on vérifie que le résultat attendu apparaît,
    plutôt que de deviner un message d'erreur précis dont le texte varie selon la configuration
    système), puis un kinit optionnel DANS cette même session (nécessaire si l'utilisateur cible
    a sa propre identité Kerberos), puis la commande réelle avec un marqueur sentinelle unique
    pour capturer sa sortie et son code de sortie sans ambiguïté. Ne lève jamais. Le mot de passe
    n'est jamais journalisé — seulement envoyé sur le canal.

    `on_progress(msg, pct)`, si fourni, est appelé à chaque changement de phase (connexion,
    élévation, kinit, commande) — pas de progression continue PENDANT une phase (le sentinelle
    reste un seul appel bloquant), mais le libellé affiché reflète correctement laquelle des
    quatre est en cours, notamment la dernière ("Exécution de la commande…") qui est souvent la
    plus longue et qu'un appelant pourrait sinon confondre avec une authentification bloquée
    (chantier O — cas réel où un run est resté affiché "Authentification Kerberos…" alors que la
    commande réelle tournait déjà depuis longtemps).

    Limite assumée (même famille que le compromis déjà accepté pour _kinit) : la détection de
    succès/échec de chaque étape intermédiaire repose sur des heuristiques de flux shell (motifs
    dans la sortie brute), pas sur un code de sortie structuré — un prompt shell inhabituel ou un
    message sudo non standard peut faire échouer la détection même si l'élévation a réellement
    réussi (ou l'inverse). Un compromis pragmatique, pas une garantie à 100 %.
    """
    if on_progress:
        on_progress("Connexion au nœud edge…", 10)
    client = _connect(ssh_cfg)
    try:
        channel = client.invoke_shell()
        _read_until(channel, markers=["$", "#"], timeout=_SHELL_BANNER_TIMEOUT_S)

        if on_progress:
            on_progress(f"Élévation vers « {elevation_cfg.target_user} »…", 25)
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
            if on_progress:
                on_progress("Authentification Kerberos…", 45)
            channel.send(f"kinit {krb_cfg.principal}\n")
            _buf, marker = _read_until(channel, markers=["assword"], timeout=_KINIT_PROMPT_TIMEOUT_S)
            if marker is None:
                return False, "kinit : délai dépassé en attendant l'invite de mot de passe."
            channel.send(krb_cfg.password + "\n")

        if on_progress:
            on_progress("Exécution de la commande…", 60)
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
        _close_all(client)


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
