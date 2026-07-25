"""
DataScheduler — tests/test_crypto.py
Teste database/crypto.py contre le vrai Gestionnaire d'identification Windows, mais
sous un service/clé de test dédié — jamais l'entrée réelle "DataScheduler"/"master_key"
utilisée par l'application.
"""

import keyring
import pytest

from database import crypto


@pytest.fixture(autouse=True)
def isolated_keyring_entry(monkeypatch):
    """Redirige crypto vers une entrée de test, isolée de la vraie clé maître de l'app."""
    monkeypatch.setattr(crypto, "_SERVICE_NAME", "DataScheduler-tests")
    monkeypatch.setattr(crypto, "_KEY_USERNAME", "master_key-test")
    monkeypatch.setattr(crypto, "_fernet", None)
    yield
    try:
        keyring.delete_password("DataScheduler-tests", "master_key-test")
    except keyring.errors.PasswordDeleteError:
        pass  # rien à nettoyer si le test n'a jamais créé de clé (ex: passthrough vide)
    crypto._fernet = None


def test_get_or_create_master_key_is_idempotent():
    key1 = crypto.get_or_create_master_key()
    key2 = crypto.get_or_create_master_key()
    assert key1 == key2


def test_encrypt_decrypt_round_trip():
    plain = "SuperSecretOracle123!"
    ciphertext = crypto.encrypt(plain)
    assert ciphertext != plain
    assert crypto.decrypt(ciphertext) == plain


def test_encrypt_empty_string_is_passthrough():
    assert crypto.encrypt("") == ""
    assert crypto.decrypt("") == ""


def test_decrypt_invalid_token_raises_value_error():
    with pytest.raises(ValueError):
        crypto.decrypt("not-a-valid-fernet-token")


def test_is_encrypted_distinguishes_plaintext_from_ciphertext():
    ciphertext = crypto.encrypt("hunter2")
    assert crypto.is_encrypted(ciphertext) is True
    assert crypto.is_encrypted("hunter2") is False
    assert crypto.is_encrypted("") is True
