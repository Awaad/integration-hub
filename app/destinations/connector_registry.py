from __future__ import annotations
from typing import Dict

from app.destinations.registry import DestinationConnector
from app.destinations.sample_passthrough_connector import PassthroughDestinationConnector
from app.destinations.evler101.connector import Evler101HostedFeedConnector


_DESTINATIONS: Dict[str, DestinationConnector] = {
    "passthrough": PassthroughDestinationConnector(),
    "101evler": Evler101HostedFeedConnector(),
}


def get_destination_connector(destination: str) -> DestinationConnector:
    key = destination.lower().strip()
    if key not in _DESTINATIONS:
        raise KeyError(f"No destination connector registered for destination={destination}")
    return _DESTINATIONS[key]


def supported_destinations() -> list[str]:
    return sorted(_DESTINATIONS.keys())