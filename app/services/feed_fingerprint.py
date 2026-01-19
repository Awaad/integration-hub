from __future__ import annotations
import hashlib
import json
from typing import Any

def stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def compute_feed_fingerprint(*, destination: str, config: dict, listing_summaries: list[dict]) -> str:
    payload = {
        "destination": destination,
        "config": config,
        "listings": listing_summaries,  # stable order
    }
    raw = stable_json(payload).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
