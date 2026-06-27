"""
Encrypted credential storage for MyShell.

Credentials are stored in ~/.myshell_vault.dat encrypted with Fernet
(AES-128-CBC + HMAC). The key is derived from the master password via
PBKDF2-HMAC-SHA256. The master password is NEVER saved to disk.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

__all__ = ["InvalidToken", "VAULT_PATH", "vault_exists", "create_vault", "unlock", "save"]

VAULT_PATH = Path.home() / ".myshell_vault.dat"
ITERATIONS = 600_000


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a Fernet key (32 bytes, url-safe base64) from the master password."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def _write(salt: bytes, key: bytes, data: dict[str, Any]) -> None:
    token = Fernet(key).encrypt(json.dumps(data).encode("utf-8"))
    blob = {
        "salt": base64.b64encode(salt).decode("ascii"),
        "data": base64.b64encode(token).decode("ascii"),
    }
    VAULT_PATH.write_text(json.dumps(blob), encoding="utf-8")


def vault_exists() -> bool:
    return VAULT_PATH.exists()


def create_vault(password: str) -> bytes:
    """Create an empty vault and return the derived key."""
    salt = os.urandom(16)
    key = _derive_key(password, salt)
    _write(salt, key, {})
    return key


def unlock(password: str) -> tuple[bytes, dict[str, Any]]:
    """Unlock the vault. Raises InvalidToken if the password is wrong."""
    blob = json.loads(VAULT_PATH.read_text(encoding="utf-8"))
    salt = base64.b64decode(blob["salt"])
    key = _derive_key(password, salt)
    token = base64.b64decode(blob["data"])
    data = json.loads(Fernet(key).decrypt(token).decode("utf-8"))  # -> InvalidToken if wrong
    return key, data


def save(key: bytes, data: dict[str, Any]) -> None:
    """Save the data reusing the vault's existing salt."""
    blob = json.loads(VAULT_PATH.read_text(encoding="utf-8"))
    salt = base64.b64decode(blob["salt"])
    _write(salt, key, data)
