from __future__ import annotations
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.canonical.v1.listing import ListingCanonicalV1
from app.destinations.mapping_base import MappingCheckResult, MappingKeySet
from app.models.destination_enum_mapping import DestinationEnumMapping
from app.models.geo_country import GeoCountry
from app.models.geo_city import GeoCity
from app.models.geo_area import GeoArea
from app.models.destination_geo_mapping import DestinationGeoMapping


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

        
        
        # address always exists (default_factory), so this always emits a key and surfaces missing data
        cc = (listing.address.country or "").strip().upper()
        city = _slug(listing.address.city)
        area = _slug(listing.address.area)
        geo_keys.add(f"{cc}:{city}:{area}")

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
        missing_geo: set[str] = set()
        warnings: list[dict] = []

        # Check enum mappings in DestinationEnumMapping (same way as 101evler)
        for ns, skeys in keys.enum_keys.items():
            for k in skeys:
                if k.startswith("<"):
                    missing_enum[ns].add(k)
                    continue

                found = (await db.execute(
                    select(DestinationEnumMapping.destination_value).where(
                        DestinationEnumMapping.destination == self.destination,
                        DestinationEnumMapping.namespace == ns,
                        DestinationEnumMapping.source_key == k,
                    )
                )).scalar_one_or_none()

                if not found:
                    missing_enum[ns].add(k)

        # geo
        country_cache: dict[str, GeoCountry | None] = {}
       
        for key in keys.geo_keys:
            # key format must be "city:area"
            parts = key.split(":", 2)
            if len(parts) != 3:
                missing_geo.add(key)
                continue

            cc, city_slug, area_slug = parts

            cc = (cc or "").strip().upper()
            city_slug = (city_slug or "").strip()
            area_slug = (area_slug or "").strip()

            if not cc or not city_slug or not area_slug:
                missing_geo.add(key)
                continue

            if cc not in country_cache:
                country_cache[cc] = (await db.execute(
                    select(GeoCountry).where(GeoCountry.code == cc)
                )).scalar_one_or_none()

            country = country_cache[cc]
            if not country:
                missing_geo.add(key)
                continue

            city = (await db.execute(
                select(GeoCity).where(
                    GeoCity.country_id == country.id,
                    GeoCity.slug == city_slug,
                )
            )).scalar_one_or_none()
            if not city:
                missing_geo.add(key)
                continue

            area = (await db.execute(
                select(GeoArea).where(
                    GeoArea.city_id == city.id,
                    GeoArea.slug == area_slug,
                )
            )).scalar_one_or_none()
            if not area:
                missing_geo.add(key)
                continue

            dm = (await db.execute(
                select(DestinationGeoMapping.destination_area_id).where(
                    DestinationGeoMapping.destination == self.destination,
                    DestinationGeoMapping.geo_area_id == area.id,
                )
            )).scalar_one_or_none()

            if not dm:
                missing_geo.add(key)
        

        ok = (all(len(v) == 0 for v in missing_enum.values()) and len(missing_geo) == 0)

        return MappingCheckResult(
            ok=ok,
            missing=MappingKeySet(enum_keys=missing_enum, geo_keys=missing_geo),
            warnings=warnings,
        )
