from __future__ import annotations

import base64
import hmac
import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class MediaSignature:
    sig: str  # base64url


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    s = s.strip()
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def sign_media_url(*, secret: str, media_id: str, expires: int, variant: str, kid: str) -> MediaSignature:
    variant = variant.strip().lower()
    media_id = media_id.strip()
    expires = int(expires)
    kid = kid.strip()
    key = _b64url_decode(secret)

    msg = f"v1.{media_id}.{expires}.{variant}.{kid}".encode("utf-8")
    mac = hmac.new(key, msg, hashlib.sha256).digest()
    return MediaSignature(sig=_b64url(mac))


def verify_media_sig(*, secret: str, media_id: str, expires: int, variant: str, kid: str, sig: str) -> bool:
    expected = sign_media_url(secret=secret, media_id=media_id, expires=expires, variant=variant, kid=kid).sig
    return hmac.compare_digest(expected, sig)
