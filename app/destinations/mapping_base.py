from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

from app.canonical.v1.listing import ListingCanonicalV1

@dataclass(frozen=True)
class MappingKeySet:
    """
    Unique keys required to export a partner's listings for a destination.
    These are NOT destination IDs; they are canonical "source keys" that must be mapped.
    """
    enum_keys: dict[str, set[str]]          # namespace -> set[source_key]
    geo_keys: set[str]                      # e.g. "city_slug:area_slug" or other plugin-defined scheme

@dataclass(frozen=True)
class MappingCheckResult:
    ok: bool
    missing: MappingKeySet
    warnings: list[dict]

class DestinationMappingPlugin(Protocol):
    destination: str

    def required_mapping_keys(self, listing: ListingCanonicalV1) -> MappingKeySet:
        """
        Extract mapping keys required for this listing.
        """
        ...

    async def check_mappings(
        self,
        *,
        db,
        tenant_id: str,
        partner_id: str,
        keys: MappingKeySet,
    ) -> MappingCheckResult:
        """
        Given aggregated keys across listings, return which are missing in DB.
        DB access allowed here.
        """
        ...
