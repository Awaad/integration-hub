from __future__ import annotations

from app.destinations.feeds.registry import get_feed_plugin


def build_public_feed_url(*, public_base_url: str, partner_id: str, destination: str, token: str) -> str:
    dest = destination.lower().strip()
    ext = get_feed_plugin(dest).format
    base = public_base_url.rstrip("/")
    return f"{base}/v1/feeds/{partner_id}/{dest}.{ext}?token={token}"
