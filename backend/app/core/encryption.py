"""Encryption for connector credentials at rest (architecture plan, section 5).

A single Fernet key (DATAFORGE_MASTER_KEY / settings.encryption_key) encrypts
DataSource connection configs directly — simpler than a full DEK-per-credential
envelope scheme, and sufficient for a single-tenant self-hosted deployment.
Kept behind this narrow interface so a future move to per-credential envelope
encryption or a KMS/Vault-backed key doesn't touch call sites.
"""

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings
from app.core.errors import DataForgeError


class DecryptionError(DataForgeError):
    status_code = 500


def _fernet() -> Fernet:
    return Fernet(settings.encryption_key.encode())


def encrypt_json(data: dict[str, Any]) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_json(token: str) -> dict[str, Any]:
    try:
        raw = _fernet().decrypt(token.encode())
    except InvalidToken as exc:
        raise DecryptionError("Could not decrypt stored connection credentials") from exc
    return json.loads(raw)
