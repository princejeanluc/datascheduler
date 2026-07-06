"""
DataScheduler — core/email.py
Envoi d'emails de notification via SMTP (STARTTLS optionnel).
"""

import logging
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  DATACLASS DE CONFIGURATION
# ──────────────────────────────────────────────

@dataclass
class SmtpConfig:
    host:         str
    port:         int  = 587
    username:     str | None = None
    password:     str | None = None
    use_tls:      bool = True
    from_address: str  = ""
    timeout:      int  = 30


# ──────────────────────────────────────────────
#  RÉSULTATS
# ──────────────────────────────────────────────

@dataclass
class SendResult:
    success: bool
    error:   str   = ""
    duration_s: float = 0.0


@dataclass
class ConnectionTestResult:
    success: bool
    message: str


# ──────────────────────────────────────────────
#  ENVOI
# ──────────────────────────────────────────────

class EmailSender:
    """Envoie des emails de notification via un profil SMTP."""

    def __init__(self, config: SmtpConfig):
        self.config = config

    def send(self, to: list[str], subject: str, body: str,
              attachment: Path | None = None) -> SendResult:
        """
        Envoie un email texte, avec pièce jointe optionnelle.
        Retourne un SendResult (ne lève jamais d'exception).
        """
        start = datetime.now()
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"]    = self.config.from_address
            msg["To"]      = ", ".join(to)
            msg.set_content(body)

            if attachment is not None:
                attachment = Path(attachment)
                data = attachment.read_bytes()
                msg.add_attachment(
                    data,
                    maintype="application",
                    subtype="octet-stream",
                    filename=attachment.name,
                )

            with smtplib.SMTP(self.config.host, self.config.port,
                               timeout=self.config.timeout) as server:
                server.ehlo()
                if self.config.use_tls:
                    server.starttls()
                    server.ehlo()
                if self.config.username and self.config.password:
                    server.login(self.config.username, self.config.password)
                server.send_message(msg)

            duration = (datetime.now() - start).total_seconds()
            logger.info("Email envoyé à %s (%.1fs)", to, duration)
            return SendResult(success=True, duration_s=round(duration, 2))

        except Exception as e:
            logger.error("Erreur envoi email : %s", e)
            return SendResult(success=False, error=str(e))

    def test_connection(self) -> ConnectionTestResult:
        """
        Vérifie la connexion/authentification SMTP sans envoyer de mail.
        Retourne un ConnectionTestResult (ne lève jamais d'exception).
        """
        try:
            with smtplib.SMTP(self.config.host, self.config.port,
                               timeout=self.config.timeout) as server:
                server.ehlo()
                if self.config.use_tls:
                    server.starttls()
                    server.ehlo()
                if self.config.username and self.config.password:
                    server.login(self.config.username, self.config.password)
            return ConnectionTestResult(success=True, message="Connexion SMTP réussie.")
        except Exception as e:
            return ConnectionTestResult(success=False, message=str(e))


# ──────────────────────────────────────────────
#  HELPER : construire depuis un profil DB
# ──────────────────────────────────────────────

def config_from_profile(profile) -> SmtpConfig:
    return SmtpConfig(
        host=profile.host,
        port=profile.port,
        username=profile.username,
        password=profile.password,
        use_tls=profile.use_tls,
        from_address=profile.from_address,
    )
