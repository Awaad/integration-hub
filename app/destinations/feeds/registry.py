from __future__ import annotations
from typing import Dict
from app.destinations.feeds.base import HostedFeedPlugin
from app.destinations.evler101.feed_plugin import Evler101FeedPlugin

_PLUGINS: Dict[str, HostedFeedPlugin] = {
    "101evler": Evler101FeedPlugin(),
}

def get_feed_plugin(destination: str) -> HostedFeedPlugin:
    key = destination.lower().strip()
    if key not in _PLUGINS:
        raise KeyError(f"No hosted feed plugin registered for destination={destination}")
    return _PLUGINS[key]
