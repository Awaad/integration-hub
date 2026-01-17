from __future__ import annotations
from typing import Dict

from app.projections.base import ListingProjector
from app.projections.sample_passthrough import PassthroughProjector  # added below

_PROJECTORS: Dict[str, ListingProjector] = {
    "passthrough": PassthroughProjector(),
}

def get_projector(destination: str) -> ListingProjector:
    key = destination.lower().strip()
    if key not in _PROJECTORS:
        raise KeyError(f"No projector registered for destination={destination}")
    return _PROJECTORS[key]

def supported_projectors() -> list[str]:
    return sorted(_PROJECTORS.keys())
