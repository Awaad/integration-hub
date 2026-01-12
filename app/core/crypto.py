import json
from cryptography.fernet import Fernet

from app.core.config import settings

_fernet = Fernet(settings.credentials_encryption_key.encode("utf-8"))


def encrypt_json(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    token = _fernet.encrypt(raw)
    return token.decode("utf-8")


def decrypt_json(token: str) -> dict:
    raw = _fernet.decrypt(token.encode("utf-8"))
    return json.loads(raw.decode("utf-8"))
