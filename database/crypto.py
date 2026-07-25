"""
DataScheduler — database/crypto.py
Chiffrement au repos des mots de passe stockés en base SQLite.

Principe : une clé maître Fernet, générée une seule fois et protégée par le
Gestionnaire d'identification Windows (keyring → DPAPI, liée à la session utilisateur
Windows). Récupérée si elle existe déjà, générée seulement si absente — jamais
régénérée à chaque lancement, quel que soit le mode de lancement (source ou .exe
packagé) ou l'interpréteur utilisé.

Chaque mot de passe de profil (Oracle/FTP/SMTP/DatabaseProfile) est chiffré avec
cette clé avant écriture en base, déchiffré à la lecture — jamais stocké en clair.
"""

import logging

import keyring
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_SERVICE_NAME = "DataScheduler"
_KEY_USERNAME = "master_key"

_fernet: Fernet | None = None


def get_or_create_master_key() -> bytes:
    """
    Récupère la clé maître depuis le Gestionnaire d'identification Windows.
    La génère et la stocke seulement si elle est absente — garantit une clé unique
    par compte Windows par machine, peu importe le nombre de lancements de l'app.
    """
    existing = keyring.get_password(_SERVICE_NAME, _KEY_USERNAME)
    if existing:
        return existing.encode("utf-8")

    key = Fernet.generate_key()
    keyring.set_password(_SERVICE_NAME, _KEY_USERNAME, key.decode("utf-8"))
    logger.info("Clé maître de chiffrement générée et stockée dans le Gestionnaire "
                "d'identification Windows.")
    return key


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(get_or_create_master_key())
    return _fernet


def encrypt(plain: str) -> str:
    """Chiffre une chaîne. Renvoie un token Fernet (texte, tient dans un VARCHAR(255))."""
    if not plain:
        return plain
    return _get_fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    """Déchiffre un token Fernet produit par encrypt(). Lève ValueError si invalide."""
    if not ciphertext:
        return ciphertext
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("Jeton chiffré invalide ou clé maître incorrecte.") from e


def is_encrypted(value: str) -> bool:
    """
    Détecte si une valeur est déjà un token Fernet (par opposition à un mot de passe
    encore en clair issu d'une base pré-chiffrement) — utilisé par la migration
    one-shot dans database/db_manager.py.
    """
    if not value:
        return True
    try:
        _get_fernet().decrypt(value.encode("utf-8"))
        return True
    except (InvalidToken, ValueError):
        return False
