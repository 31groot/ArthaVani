"""Encrypted-at-rest storage helpers for Groww credentials."""
from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken

from config.settings import settings


def _fernet() -> Fernet:
    key = settings.GROWW_CREDENTIALS_ENCRYPTION_KEY
    if not key:
        raise RuntimeError(
            "GROWW_CREDENTIALS_ENCRYPTION_KEY is not configured."
        )
    return Fernet(key.encode())


def encrypt_credentials(credentials: dict[str, str]) -> str:
    payload = json.dumps(credentials, separators=(",", ":")).encode()
    return _fernet().encrypt(payload).decode()


def decrypt_credentials(ciphertext: str) -> dict[str, str]:
    try:
        payload = _fernet().decrypt(ciphertext.encode())
        result = json.loads(payload.decode())
    except (InvalidToken, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Stored Groww credentials could not be decrypted.") from exc

    if not isinstance(result, dict):
        raise RuntimeError("Stored Groww credentials are invalid.")

    return {str(key): str(value) for key, value in result.items()}
