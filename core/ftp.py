"""
DataScheduler — core/ftp.py
Upload de fichiers vers FTP / FTPS / SFTP.

Protocoles :
  FTP  — FTP standard (non chiffré)
  FTPS — FTP over TLS explicite (AUTH TLS)
  SFTP — SSH File Transfer Protocol (via paramiko)
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  DATACLASS DE CONFIGURATION
# ──────────────────────────────────────────────

@dataclass
class FtpConfig:
    host:       str
    port:       int
    username:   str
    password:   str
    protocol:   str = "FTP"    # "FTP" | "FTPS" | "SFTP"
    timeout:    int = 30


# ──────────────────────────────────────────────
#  RÉSULTATS
# ──────────────────────────────────────────────

@dataclass
class UploadResult:
    success:     bool
    remote_path: str  = ""
    bytes_sent:  int  = 0
    duration_s:  float = 0.0
    error:       str  = ""


@dataclass
class ConnectionTestResult:
    success: bool
    message: str


# ──────────────────────────────────────────────
#  UPLOADER
# ──────────────────────────────────────────────

class FtpUploader:
    """
    Upload un fichier local vers un serveur FTP / FTPS / SFTP.
    Le protocole est sélectionné automatiquement depuis FtpConfig.protocol.
    """

    def __init__(self, config: FtpConfig):
        self.config = config

    # ── API publique ─────────────────────────

    def upload(self, local_path: Path, remote_path: str) -> UploadResult:
        """
        Envoie local_path vers remote_path sur le serveur.
        Crée les répertoires distants si nécessaire.
        Retourne un UploadResult (ne lève jamais d'exception).
        """
        proto = self.config.protocol.upper()
        try:
            if proto == "SFTP":
                return self._upload_sftp(local_path, remote_path)
            elif proto == "FTPS":
                return self._upload_ftps(local_path, remote_path)
            else:
                return self._upload_ftp(local_path, remote_path)
        except Exception as e:
            logger.error("Erreur upload %s → %s : %s", local_path, remote_path, e)
            return UploadResult(success=False, error=str(e))

    def test_connection(self) -> ConnectionTestResult:
        """
        Vérifie que la connexion est possible sans transférer de fichier.
        Retourne un ConnectionTestResult (ne lève jamais d'exception).
        """
        proto = self.config.protocol.upper()
        try:
            if proto == "SFTP":
                return self._test_sftp()
            elif proto == "FTPS":
                return self._test_ftps()
            else:
                return self._test_ftp()
        except Exception as e:
            return ConnectionTestResult(success=False, message=str(e))

    # ── FTP ──────────────────────────────────

    def _upload_ftp(self, local_path: Path, remote_path: str) -> UploadResult:
        import ftplib
        start = datetime.now()
        size  = local_path.stat().st_size

        with ftplib.FTP(timeout=self.config.timeout) as ftp:
            ftp.connect(self.config.host, self.config.port)
            ftp.login(self.config.username, self.config.password)
            self._ftp_makedirs(ftp, remote_path)
            with open(local_path, "rb") as f:
                ftp.storbinary(f"STOR {remote_path}", f)

        duration = (datetime.now() - start).total_seconds()
        logger.info("FTP upload OK : %s → %s (%.1f Ko, %.1fs)",
                    local_path.name, remote_path, size / 1024, duration)
        return UploadResult(success=True, remote_path=remote_path,
                            bytes_sent=size, duration_s=round(duration, 2))

    def _test_ftp(self) -> ConnectionTestResult:
        import ftplib
        with ftplib.FTP(timeout=self.config.timeout) as ftp:
            ftp.connect(self.config.host, self.config.port)
            ftp.login(self.config.username, self.config.password)
            welcome = ftp.getwelcome()
        return ConnectionTestResult(success=True, message=f"Connexion FTP réussie. {welcome}")

    # ── FTPS ─────────────────────────────────

    def _upload_ftps(self, local_path: Path, remote_path: str) -> UploadResult:
        import ftplib
        start = datetime.now()
        size  = local_path.stat().st_size

        with ftplib.FTP_TLS(timeout=self.config.timeout) as ftp:
            ftp.connect(self.config.host, self.config.port)
            ftp.login(self.config.username, self.config.password)
            ftp.prot_p()   # chiffrement des données
            self._ftp_makedirs(ftp, remote_path)
            with open(local_path, "rb") as f:
                ftp.storbinary(f"STOR {remote_path}", f)

        duration = (datetime.now() - start).total_seconds()
        logger.info("FTPS upload OK : %s → %s (%.1f Ko, %.1fs)",
                    local_path.name, remote_path, size / 1024, duration)
        return UploadResult(success=True, remote_path=remote_path,
                            bytes_sent=size, duration_s=round(duration, 2))

    def _test_ftps(self) -> ConnectionTestResult:
        import ftplib
        with ftplib.FTP_TLS(timeout=self.config.timeout) as ftp:
            ftp.connect(self.config.host, self.config.port)
            ftp.login(self.config.username, self.config.password)
            ftp.prot_p()
            welcome = ftp.getwelcome()
        return ConnectionTestResult(success=True, message=f"Connexion FTPS réussie. {welcome}")

    # ── SFTP ─────────────────────────────────

    def _upload_sftp(self, local_path: Path, remote_path: str) -> UploadResult:
        import paramiko
        start = datetime.now()
        size  = local_path.stat().st_size

        transport = paramiko.Transport((self.config.host, self.config.port))
        transport.connect(username=self.config.username, password=self.config.password)
        try:
            sftp = paramiko.SFTPClient.from_transport(transport)
            self._sftp_makedirs(sftp, remote_path)
            sftp.put(str(local_path), remote_path)
            sftp.close()
        finally:
            transport.close()

        duration = (datetime.now() - start).total_seconds()
        logger.info("SFTP upload OK : %s → %s (%.1f Ko, %.1fs)",
                    local_path.name, remote_path, size / 1024, duration)
        return UploadResult(success=True, remote_path=remote_path,
                            bytes_sent=size, duration_s=round(duration, 2))

    def _test_sftp(self) -> ConnectionTestResult:
        import paramiko
        transport = paramiko.Transport((self.config.host, self.config.port))
        transport.connect(username=self.config.username, password=self.config.password)
        try:
            sftp = paramiko.SFTPClient.from_transport(transport)
            sftp.listdir(".")
            sftp.close()
        finally:
            transport.close()
        return ConnectionTestResult(
            success=True,
            message=f"Connexion SFTP réussie ({self.config.host}:{self.config.port})"
        )

    # ── Helpers ──────────────────────────────

    @staticmethod
    def _ftp_makedirs(ftp, remote_path: str) -> None:
        """Crée récursivement les répertoires distants (FTP/FTPS)."""
        import ftplib
        remote_dir = remote_path.rsplit("/", 1)[0] if "/" in remote_path else ""
        if not remote_dir:
            return
        parts = remote_dir.strip("/").split("/")
        current = ""
        for part in parts:
            current = f"{current}/{part}"
            try:
                ftp.mkd(current)
            except ftplib.error_perm:
                pass   # répertoire existe déjà

    @staticmethod
    def _sftp_makedirs(sftp, remote_path: str) -> None:
        """Crée récursivement les répertoires distants (SFTP)."""
        remote_dir = remote_path.rsplit("/", 1)[0] if "/" in remote_path else ""
        if not remote_dir:
            return
        parts = remote_dir.strip("/").split("/")
        current = ""
        for part in parts:
            current = f"{current}/{part}"
            try:
                sftp.mkdir(current)
            except OSError:
                pass   # répertoire existe déjà


# ──────────────────────────────────────────────
#  HELPERS : construire depuis un profil DB
# ──────────────────────────────────────────────

def config_from_profile(profile) -> FtpConfig:
    proto = profile.protocol.value if hasattr(profile.protocol, "value") else str(profile.protocol)
    return FtpConfig(
        host=profile.host,
        port=profile.port,
        username=profile.username,
        password=profile.password,
        protocol=proto,
    )


def resolve_remote_path(remote_path_tpl: str, filename_tpl: str) -> str:
    """
    Résout les templates de chemin et de nom de fichier avec la date courante.
    Ex : "/export/{yyyy}/{MM}/" + "ventes_{yyyyMMdd}.csv" → "/export/2026/06/ventes_20260608.csv"
    """
    from core.oracle import resolve_template
    now = datetime.now()
    remote_dir  = resolve_template(remote_path_tpl, now).rstrip("/")
    filename    = resolve_template(filename_tpl, now)
    return f"{remote_dir}/{filename}"
