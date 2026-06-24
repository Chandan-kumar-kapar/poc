from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings, get_settings


@dataclass
class KeySet:
    """Holds the active private signing key and all public keys (by kid)."""

    active_kid: str
    private_pem: str
    public_pems: Dict[str, str]  # kid -> public key PEM


def _generate_in_memory_keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


def _load_from_disk(settings: Settings) -> KeySet:
    private_pem = Path(settings.jwt_private_key_path).read_text()

    public_pems: Dict[str, str] = {}
    jwks_dir = Path(settings.jwt_public_keys_path)
    if jwks_dir.is_dir():
        # Each public key file is named "<kid>.pem".
        for f in sorted(jwks_dir.glob("*.pem")):
            kid = f.stem
            public_pems[kid] = f.read_text()
    if not public_pems:
        raise RuntimeError(
            f"No public keys (*.pem) found in {settings.jwt_public_keys_path}"
        )
    if settings.jwt_active_kid not in public_pems:
        raise RuntimeError(
            f"JWT_ACTIVE_KID '{settings.jwt_active_kid}' has no matching public key "
            f"in {settings.jwt_public_keys_path}"
        )
    return KeySet(
        active_kid=settings.jwt_active_kid,
        private_pem=private_pem,
        public_pems=public_pems,
    )


@lru_cache
def get_keyset() -> KeySet:
    settings = get_settings()
    if settings.testing or os.getenv("POC_INMEMORY_KEYS") == "1":
        priv, pub = _generate_in_memory_keypair()
        kid = settings.jwt_active_kid or "test-key"
        return KeySet(active_kid=kid, private_pem=priv, public_pems={kid: pub})
    return _load_from_disk(settings)
