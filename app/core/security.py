import base64
import hashlib
import secrets
from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class ApiKeyParts:
    prefix: str
    plain: str
    hashed: str


def generate_api_key(prefix_len: int = 8) -> ApiKeyParts:
    # Example: hk_live_<random>
    raw = secrets.token_urlsafe(32)
    prefix = raw[:prefix_len]
    plain = f"hk_{prefix}_{raw}"
    hashed = hash_api_key(plain)
    return ApiKeyParts(prefix=prefix, plain=plain, hashed=hashed)


def hash_api_key(plain: str) -> str:
    # Pepper protects against rainbow tables if DB leaks.
    salted = (plain + settings.api_key_pepper).encode("utf-8")
    digest = hashlib.sha256(salted).digest()
    return base64.b64encode(digest).decode("utf-8")
