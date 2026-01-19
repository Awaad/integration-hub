from __future__ import annotations
from typing import Dict

from app.destinations.base import DestinationConnector


_DESTINATIONS: dict[str, DestinationConnector] = {}

def register(connector: DestinationConnector) -> None:
    _DESTINATIONS[connector.destination.lower().strip()] = connector


def get_destination_connector(destination: str) -> DestinationConnector:
    key = destination.lower().strip()
    if key not in _DESTINATIONS:
        raise KeyError(f"No destination connector registered for destination={destination}")
    return _DESTINATIONS[key]


def supported_destinations() -> list[str]:
    return sorted(_DESTINATIONS.keys())