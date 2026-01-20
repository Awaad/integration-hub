from __future__ import annotations
import hashlib
import json
from typing import Any

def _stable_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def hash_config(config: dict) -> str:
    return sha256_hex(_stable_json_bytes(config))

def hash_listing_inputs(listing_summaries: list[dict]) -> str:
    # listing_summaries must be stable-order already
    return sha256_hex(_stable_json_bytes(listing_summaries))

def hash_fingerprint(*, destination: str, config_hash: str, input_hash: str) -> str:
    return sha256_hex(_stable_json_bytes({
        "destination": destination,
        "config_hash": config_hash,
        "input_hash": input_hash,
    }))
