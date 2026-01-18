from __future__ import annotations
from typing import Dict

from app.destinations.mapping_base import DestinationMappingPlugin
from app.destinations.evler101.mapping_plugin import Evler101MappingPlugin

_PLUGINS: Dict[str, DestinationMappingPlugin] = {
    "101evler": Evler101MappingPlugin(),
}

def get_mapping_plugin(destination: str) -> DestinationMappingPlugin:
    key = destination.lower().strip()
    if key not in _PLUGINS:
        raise KeyError(f"No mapping plugin registered for destination={destination}")
    return _PLUGINS[key]
