from __future__ import annotations
from typing import Any

DEFAULT_SENSITIVE_KEYS = {
    "password", "pass", "pwd",
    "secret", "client_secret",
    "token", "access_token", "refresh_token",
    "api_key", "apikey",
    "authorization", "auth",
}

REDACTED = "**********"

def redact_payload(value: Any, *, extra_keys: set[str] | None = None) -> Any:
    sensitive = set(DEFAULT_SENSITIVE_KEYS)
    if extra_keys:
        sensitive |= {k.lower() for k in extra_keys}

    def _walk(v: Any) -> Any:
        if isinstance(v, dict):
            out = {}
            for k, vv in v.items():
                if isinstance(k, str) and k.lower() in sensitive:
                    out[k] = REDACTED
                else:
                    out[k] = _walk(vv)
            return out
        if isinstance(v, list):
            return [_walk(x) for x in v]
        return v

    return _walk(value)
