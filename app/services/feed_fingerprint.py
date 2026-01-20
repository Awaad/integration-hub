from __future__ import annotations
import hashlib
import json
from typing import Any

from app.services.feed_hashes import hash_config, hash_fingerprint, hash_listing_inputs



def compute_feed_fingerprint(*, destination: str, config: dict, listing_summaries: list[dict]) -> str:
    # listing_summaries must be stable-order already
    config_hash = hash_config(config)
    input_hash = hash_listing_inputs(listing_summaries)
    return hash_fingerprint(destination=destination, config_hash=config_hash, input_hash=input_hash)
