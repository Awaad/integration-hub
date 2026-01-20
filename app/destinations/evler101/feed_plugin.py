from __future__ import annotations

import hashlib
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.canonical.v1.listing import ListingCanonicalV1
from app.models.listing import Listing
from app.models.agent_external_identity import AgentExternalIdentity
from app.models.destination_enum_mapping import DestinationEnumMapping
from app.models.destination_geo_mapping import DestinationGeoMapping
from app.models.geo_country import GeoCountry
from app.models.geo_city import GeoCity
from app.models.geo_area import GeoArea
from app.services.feeds.evler101_xml import build_101evler_xml, Evler101Ad
from app.destinations.feeds.base import FeedBuildOutput
from app.destinations.evler101.ad_projection import project_ad_fields


def _slug(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "-")


async def _enum(db: AsyncSession, *, ns: str, key: str) -> str | None:
    row = (await db.execute(select(DestinationEnumMapping.destination_value).where(
        DestinationEnumMapping.destination == "101evler",
        DestinationEnumMapping.namespace == ns,
        DestinationEnumMapping.source_key == key,
    ))).scalar_one_or_none()
    return row


async def _area_id_for(db: AsyncSession, *, country_code: str, city_slug: str, area_slug: str) -> str | None:
    country = (await db.execute(select(GeoCountry).where(GeoCountry.code == country_code))).scalar_one_or_none()
    if not country:
        return None
    city = (await db.execute(select(GeoCity).where(GeoCity.country_id == country.id, GeoCity.slug == city_slug))).scalar_one_or_none()
    if not city:
        return None
    area = (await db.execute(select(GeoArea).where(GeoArea.city_id == city.id, GeoArea.slug == area_slug))).scalar_one_or_none()
    if not area:
        return None
    m = (await db.execute(select(DestinationGeoMapping.destination_area_id).where(
        DestinationGeoMapping.destination == "101evler",
        DestinationGeoMapping.geo_area_id == area.id,
    ))).scalar_one_or_none()
    return m


class Evler101FeedPlugin:
    destination = "101evler"
    format = "xml"

    async def build(self, *, db: AsyncSession, tenant_id: str, partner_id: str, config: dict[str, Any]) -> FeedBuildOutput:
        # Load listings for partner
        rows = (await db.execute(select(Listing).where(
            Listing.tenant_id == tenant_id,
            Listing.partner_id == partner_id,
            Listing.schema == "canonical.listing",
            Listing.schema_version == "1.0",
        ))).scalars().all()

        warnings: list[dict[str, Any]] = []
        ads: list[Evler101Ad] = []

        for r in rows:
            can = ListingCanonicalV1.model_validate(r.payload)

            # Resolve required mappings
            prop_type = getattr(can.property, "property_type", None) if can.property else None
            type_id = await _enum(db, ns="property_type", key=str(prop_type)) if prop_type else None
            if not type_id:
                warnings.append({"listing_id": can.canonical_id, "code": "MISSING_TYPE_ID", "message": f"Unmapped property_type={prop_type}"})
                continue

            if not can.list_price:
                warnings.append({"listing_id": can.canonical_id, "code": "MISSING_PRICE", "message": "Missing list_price"})
                continue

            currency_id = await _enum(db, ns="currency", key=str(can.list_price.currency))
            if not currency_id:
                warnings.append({"listing_id": can.canonical_id, "code": "MISSING_CURRENCY", "message": f"Unmapped currency={can.list_price.currency}"})
                continue

            city_slug = _slug(can.address.city) if can.address else ""
            area_slug = _slug(getattr(can.address, "area", None) or "") if can.address else ""
            area_id = await _area_id_for(db, country_code="NCY", city_slug=city_slug, area_slug=area_slug)
            if not area_id:
                warnings.append({"listing_id": can.canonical_id, "code": "MISSING_AREA_ID", "message": f"Unmapped geo {city_slug}:{area_slug}"})
                continue

            # Agent external id -> first_realtor_id (docs uses realtor IDs) :contentReference[oaicite:25]{index=25}
            realtor_id = (await db.execute(select(AgentExternalIdentity.external_agent_id).where(
                AgentExternalIdentity.tenant_id == tenant_id,
                AgentExternalIdentity.partner_id == partner_id,
                AgentExternalIdentity.agent_id == r.agent_id,
                AgentExternalIdentity.destination == "101evler",
                AgentExternalIdentity.is_active.is_(True),
            ))).scalar_one_or_none()

            # Room count mapping: ideally canonical provides bedrooms+livingRooms -> "3+1"
            room_count_key = None
            if can.property:
                b = getattr(can.property, "bedrooms", None)
                lr = getattr(can.property, "living_rooms", None)
                if b is not None and lr is not None:
                    room_count_key = f"{b}+{lr}"
            room_count_id = await _enum(db, ns="rooms", key=room_count_key) if room_count_key else None

            # Title type (optional)
            title_type_key = getattr(getattr(can, "property", None), "title_type", None)
            title_type_id = await _enum(db, ns="title_type", key=str(title_type_key)) if title_type_key else None

            fields, proj_warn = project_ad_fields(
                listing=can,
                updated_at=r.updated_at,
                type_id=str(type_id),
                area_id=str(area_id),
                currency_id=str(currency_id),
                first_realtor_id=str(realtor_id) if realtor_id else None,
                room_count_id=str(room_count_id) if room_count_id else None,
                title_type_id=str(title_type_id) if title_type_id else None,
            )
            for w in proj_warn:
                warnings.append({"listing_id": can.canonical_id, "code": w.code, "message": w.message})

            # Pictures: URL dedupe rule; order_by required :contentReference[oaicite:26]{index=26}
            pics: list[dict[str, Any]] = []
            images = [m for m in (can.media or []) if m.type == "image"]
            images_sorted = sorted(images, key=lambda m: (m.order, m.id))
            for idx, m in enumerate(images_sorted, start=1):
                pic = {"picture_url": str(m.url), "order_by": idx}
                # Optional group_id if provided in metadata (future)
                meta = getattr(m, "metadata", None) or {}
                if isinstance(meta, dict) and meta.get("group_id") is not None:
                    pic["group_id"] = meta["group_id"]
                pics.append(pic)

            ads.append(Evler101Ad(listing_id=can.canonical_id, fields=fields, pictures=pics))

        xml_bytes, _builder_warnings, count = build_101evler_xml(ads=ads)

        # content_hash for caching/ETag: stable over listing hashes + config
        h = hashlib.sha256(xml_bytes).hexdigest()

        return FeedBuildOutput(
            format="xml",
            bytes=xml_bytes,
            listing_count=count,
            meta={"generator": "evler101_feed_v1", "warnings": warnings},
            content_hash=h,
        )
