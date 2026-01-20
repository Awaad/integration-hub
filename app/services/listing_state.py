from __future__ import annotations
from typing import Any

def canonical_status(payload: dict[str, Any]) -> str:
    # canonical payload has "status" per our schema usage
    return str(payload.get("status") or "").lower().strip()

def is_active_status(status: str) -> bool:
    # adjust as our canonical evolves
    return status in ("active", "published", "live", "available")

def should_include_listing(*, policy: str, status: str) -> bool:
    if policy == "exclude_inactive":
        return is_active_status(status)
    if policy == "include_with_status":
        return True
    return is_active_status(status)
