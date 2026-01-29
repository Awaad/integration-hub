from __future__ import annotations
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.canonical.v1.listing import ListingCanonicalV1
from app.destinations.mapping_base import MappingCheckResult, MappingKeySet, DestinationMappingPlugin
from app.models.destination_enum_mapping import DestinationEnumMapping


DEST = "mls_demo_push"

def _slug(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "-")

@dataclass(frozen=True)
class MlsDemoPushMappingPlugin:
    destination: str = DEST

    def required_mapping_keys(self, listing: ListingCanonicalV1) -> MappingKeySet:
        enum_keys: dict[str, set[str]] = {
            "currency": set(),
            "property_category": set(),
        }
        geo_keys: set[str] = set()

        if listing.list_price and listing.list_price.currency:
            enum_keys["currency"].add(str(listing.list_price.currency))
        else:
            enum_keys["currency"].add("<missing_price>")

        if listing.property and listing.property.category:
            enum_keys["property_category"].add(str(listing.property.category))
        else:
            enum_keys["property_category"].add("<missing_category>")

        if listing.address:
            city = _slug(listing.address.city)
            area = _slug(listing.address.area)
            geo_keys.add(f"{city}:{area}")

        return MappingKeySet(enum_keys=enum_keys, geo_keys=geo_keys)

async def check_mappings(
        self,
        *,
        db: AsyncSession,
        tenant_id: str,
        partner_id: str,
        keys: MappingKeySet,
    ) -> MappingCheckResult:
        missing_enum: dict[str, set[str]] = {ns: set() for ns in keys.enum_keys.keys()} 
        warnings: list[dict] = []

        # Check enum mappings in DestinationEnumMapping (same way as 101evler)
        for ns, skeys in keys.enum_keys.items():
            for k in skeys:
                if k.startswith("<"):
                    missing_enum[ns].add(k)
                    continue

                found = (await db.execute(
                    select(DestinationEnumMapping.destination_value).where(
                        DestinationEnumMapping.destination == DEST,
                        DestinationEnumMapping.namespace == ns,
                        DestinationEnumMapping.source_key == k,
                    )
                )).scalar_one_or_none()

                if not found:
                    missing_enum[ns].add(k)

        missing_geo: set[str] = set()
        
        warnings.append({"code": "GEO_CHECK_SKIPPED", "message": "mls_demo_push demo does not enforce geo mappings yet"})

        ok = (all(len(v) == 0 for v in missing_enum.values()) and len(missing_geo) == 0)

        return MappingCheckResult(
            ok=ok,
            missing=MappingKeySet(enum_keys=missing_enum, geo_keys=missing_geo),
            warnings=warnings,
        )
