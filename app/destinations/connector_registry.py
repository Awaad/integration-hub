from __future__ import annotations
from typing import Dict

from app.destinations.registry import DestinationConnector
from app.destinations.sample_passthrough_connector import PassthroughDestinationConnector

_CONNECTORS: Dict[str, DestinationConnector] = {
    "passthrough": PassthroughDestinationConnector(),
}

def get_destination_connector(destination: str) -> DestinationConnector:
    key = destination.lower().strip()
    if key not in _CONNECTORS:
        raise KeyError(f"No destination connector registered for destination={destination}")
    return _CONNECTORS[key]

def supported_destinations() -> list[str]:
    return sorted(_CONNECTORS.keys())
