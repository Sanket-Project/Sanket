"""Symmetric encryption for secrets stored at rest (e.g. integration tokens).

A Fernet key is derived from a configured secret via SHA-256 so any string can
be used as the key material. ``integration_encryption_key`` is preferred; we
fall back to ``jwt_secret`` so local dev works without extra setup.

Fernet gives authenticated encryption (AES-128-CBC + HMAC), so a tampered or
wrong-key ciphertext fails loudly rather than returning garbage.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    settings = get_settings()
    secret = settings.integration_encryption_key or settings.jwt_secret
    return Fernet(_derive_fernet_key(secret))


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret for storage. Returns a urlsafe token string."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a value produced by ``encrypt_secret``.

    Raises ValueError if the ciphertext is tampered with or the encryption key
    has changed since it was written.
    """
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:  # pragma: no cover - defensive
        raise ValueError("could not decrypt secret (encryption key mismatch?)") from exc
