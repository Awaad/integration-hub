from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class GeneratedToken:
    plain: str
    prefix: str
    hashed: str  # hex sha256, 64 chars


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def generate_public_token(*, prefix_len: int = 10) -> GeneratedToken:
    # URL-safe bearer token (no hk_ prefix; meant for public URLs)
    raw = secrets.token_bytes(32)
    plain = _b64url(raw)
    prefix_len = min(prefix_len, len(plain))
    prefix = plain[:prefix_len]
    hashed = hash_public_token(plain)
    return GeneratedToken(plain=plain, prefix=prefix, hashed=hashed)


def hash_public_token(plain: str) -> str:
    pepper = settings.public_token_pepper.get_secret_value()
    salted = (plain + pepper).encode("utf-8")
    return hashlib.sha256(salted).hexdigest()


def generate_signing_secret() -> str:
    # secret used for HMAC signing (stored encrypted server-side)
    return _b64url(secrets.token_bytes(32))
