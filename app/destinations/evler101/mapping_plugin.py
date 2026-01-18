from __future__ import annotations
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.destinations.mapping_base import DestinationMappingPlugin, MappingKeySet, MappingCheckResult
from app.canonical.v1.listing import ListingCanonicalV1
from app.models.destination_enum_mapping import DestinationEnumMapping
from app.models.geo_country import GeoCountry
from app.models.geo_city import GeoCity
from app.models.geo_area import GeoArea
from app.models.destination_geo_mapping import DestinationGeoMapping

def _slug(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "-")


class Evler101MappingPlugin:
    destination = "101evler"

    def required_mapping_keys(self, listing: ListingCanonicalV1) -> MappingKeySet:
        enum: dict[str, set[str]] = {"property_type": set(), "currency": set(), "rooms": set()}
        geo: set[str] = set()

        prop_type = getattr(listing.property, "property_type", None) if listing.property else None
        if prop_type:
            enum["property_type"].add(str(prop_type))
        else:
            enum["property_type"].add("<missing>")

        if listing.list_price:
            enum["currency"].add(str(listing.list_price.currency))
        else:
            enum["currency"].add("<missing_price>")

        # rooms optional (only if your canonical has it)
        rooms = getattr(listing, "rooms", None) or getattr(listing, "bedrooms", None)
        if rooms is not None:
            enum["rooms"].add(str(rooms))

        city_slug = _slug(listing.address.city) if listing.address else ""
        area_slug = _slug(getattr(listing.address, "area", None) or "") if listing.address else ""
        if city_slug and area_slug:
            geo.add(f"{city_slug}:{area_slug}")
        else:
            geo.add(f"{city_slug}:{area_slug}")

        return MappingKeySet(enum_keys=enum, geo_keys=geo)

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

        dest = self.destination

        # Check enum mappings in DB
        for ns, skeys in keys.enum_keys.items():
            for k in skeys:
                if k.startswith("<"):
                    missing_enum[ns].add(k)
                    continue
                found = (await db.execute(select(DestinationEnumMapping.destination_value).where(
                    DestinationEnumMapping.destination == dest,
                    DestinationEnumMapping.namespace == ns,
                    DestinationEnumMapping.source_key == k,
                ))).scalar_one_or_none()
                if not found:
                    missing_enum[ns].add(k)

        # Geo mapping uses shared NCY catalogs
        country = (await db.execute(select(GeoCountry).where(GeoCountry.code == "NCY"))).scalar_one_or_none()
        if not country:
            missing_geo |= set(keys.geo_keys)
            warnings.append({"code": "MISSING_COUNTRY_CATALOG", "message": "GeoCountry NCY not found"})
        else:
            for key in keys.geo_keys:
                if ":" not in key:
                    missing_geo.add(key)
                    continue
                city_slug, area_slug = key.split(":", 1)
                city = (await db.execute(select(GeoCity).where(
                    GeoCity.country_id == country.id,
                    GeoCity.slug == city_slug,
                ))).scalar_one_or_none()
                if not city:
                    missing_geo.add(key)
                    continue
                area = (await db.execute(select(GeoArea).where(
                    GeoArea.city_id == city.id,
                    GeoArea.slug == area_slug,
                ))).scalar_one_or_none()
                if not area:
                    missing_geo.add(key)
                    continue
                dm = (await db.execute(select(DestinationGeoMapping).where(
                    DestinationGeoMapping.destination == dest,
                    DestinationGeoMapping.geo_area_id == area.id,
                ))).scalar_one_or_none()
                if not dm or not dm.destination_area_id:
                    missing_geo.add(key)

        missing = MappingKeySet(enum_keys=missing_enum, geo_keys=missing_geo)
        ok = (all(len(v) == 0 for v in missing_enum.values()) and len(missing_geo) == 0)
        return MappingCheckResult(ok=ok, missing=missing, warnings=warnings)
