from __future__ import annotations
import hashlib
import json
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.canonical.v1.listing import ListingCanonicalV1
from app.models.listing import Listing
from app.models.feed_snapshot import FeedSnapshot
from app.services.feed_generator import generate_xml_feed
from app.services.storage import LocalObjectStore
from app.models.partner_destination_setting import PartnerDestinationSetting
from app.services.feeds.evler101_xml import build_101evler_xml

from app.models.geo_country import GeoCountry
from app.models.geo_city import GeoCity
from app.models.geo_area import GeoArea
from app.models.destination_geo_mapping import DestinationGeoMapping



def _slug(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "-")


def _stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _city_area_slug_from_listing(can: ListingCanonicalV1) -> tuple[str, str] | None:
    """
    Returns (city_slug, area_slug) if present.
    We try address.area if exists, else fallback to address.region.
    """
    if not can.address:
        return None
    city_slug = _slug(can.address.city or "")
    # Prefer an 'area' field  else use region as area-like
    area_val = getattr(can.address, "area", None) or can.address.region or ""
    area_slug = _slug(area_val)
    if not city_slug or not area_slug:
        return None
    return city_slug, area_slug


async def _build_dynamic_area_id_map_for_101evler(
    db: AsyncSession,
    *,
    listings: list[ListingCanonicalV1],
    country_code: str = "NCY",
) -> dict[str, str]:
    """
    Build mapping: "city_slug:area_slug" -> destination_area_id
    using GeoCountry/GeoCity/GeoArea + DestinationGeoMapping.
    """
    country = (
        await db.execute(select(GeoCountry).where(GeoCountry.code == country_code))
    ).scalar_one_or_none()
    if not country:
        return {}

    # Gather unique (city_slug, area_slug) pairs from canonical listings
    pairs: set[tuple[str, str]] = set()
    city_slugs: set[str] = set()
    for can in listings:
        ca = _city_area_slug_from_listing(can)
        if not ca:
            continue
        city_slug, area_slug = ca
        pairs.add((city_slug, area_slug))
        city_slugs.add(city_slug)

    if not pairs:
        return {}

    # Fetch all destination mappings for this country/destination
    maps = (
        await db.execute(
            select(DestinationGeoMapping).where(
                DestinationGeoMapping.destination == "101evler",
                DestinationGeoMapping.geo_country_id == country.id,
            )
        )
    ).scalars().all()

    area_map_by_geo_area: dict[str, str] = {
        m.geo_area_id: m.destination_area_id
        for m in maps
        if m.geo_area_id and m.destination_area_id
    }
    if not area_map_by_geo_area:
        return {}

    # Fetch GeoCity rows for all city slugs in one query
    cities = (
        await db.execute(
            select(GeoCity).where(
                GeoCity.country_id == country.id,
                GeoCity.slug.in_(sorted(city_slugs)),
            )
        )
    ).scalars().all()

    city_by_slug = {c.slug: c for c in cities}
    city_ids = [c.id for c in cities]
    if not city_ids:
        return {}

    # Fetch GeoArea rows for those cities in one query
    areas = (
        await db.execute(
            select(GeoArea).where(
                GeoArea.city_id.in_(city_ids),
            )
        )
    ).scalars().all()

    # Index areas by (city_id, area_slug)
    area_by_city_and_slug: dict[tuple[str, str], GeoArea] = {
        (a.city_id, a.slug): a for a in areas
    }

    out: dict[str, str] = {}
    for city_slug, area_slug in pairs:
        city = city_by_slug.get(city_slug)
        if not city:
            continue
        area = area_by_city_and_slug.get((city.id, area_slug))
        if not area:
            continue
        dest_area_id = area_map_by_geo_area.get(area.id)
        if dest_area_id:
            out[f"{city_slug}:{area_slug}"] = dest_area_id

    return out


async def build_partner_feed_snapshot(
    db: AsyncSession,
    *,
    tenant_id: str,
    partner_id: str,
    destination: str,
    store: LocalObjectStore,
) -> FeedSnapshot:
    
    setting = (await db.execute(select(PartnerDestinationSetting).where(
        PartnerDestinationSetting.tenant_id == tenant_id,
        PartnerDestinationSetting.partner_id == partner_id,
        PartnerDestinationSetting.destination == destination,
    ))).scalar_one()

    cfg = setting.config or {}

    # fetch listings + their updated_at
    rows = (await db.execute(
        select(Listing).where(
            Listing.tenant_id == tenant_id,
            Listing.partner_id == partner_id,
            Listing.schema == "canonical.listing",
            Listing.schema_version == "1.0",
        )
    )).scalars().all()

    canonicals_with_meta = [
        (ListingCanonicalV1.model_validate(r.payload), (r.content_hash or ""), r.updated_at)
        for r in rows
    ]

    # For feed generator APIs that expect (canonical, updated_at)
    pairs = [(can, updated_at) for (can, _hash, updated_at) in canonicals_with_meta]
    canonicals = [can for (can, _hash, _updated_at) in canonicals_with_meta]

    # destination-specific config enrichment
    if destination == "101evler":
        # Start with manual config overrides
        area_id_map = dict(cfg.get("area_id_map") or {})

        # Fill missing keys dynamically from geo mappings
        dynamic_map = await _build_dynamic_area_id_map_for_101evler(db, listings=canonicals, country_code="NCY")
        for k, v in dynamic_map.items():
            area_id_map.setdefault(k, v)

        cfg = dict(cfg)
        cfg["area_id_map"] = area_id_map

        xml_bytes, warnings, count = build_101evler_xml(listings=pairs, config=cfg)
        feed_format = "xml"
        meta = {"generator": "101evler_xml_v1", "warnings": [w.__dict__ for w in warnings]}
    else:
        xml_bytes, _, count = generate_xml_feed(canonicals)
        warnings = []
        feed_format = "xml"
        meta = {"generator": "xml_v1"}

        # Semantic content hash (stable across XML formatting changes)
    hash_payload: dict[str, Any] = {
        "destination": destination,
        "format": feed_format,
        # include only config that affects output (avoid secrets like feed_token)
        "config": {"area_id_map": cfg.get("area_id_map", {})} if destination == "101evler" else {},
        "listings": [
            {"canonical_id": can.canonical_id, "content_hash": listing_hash}
            for (can, listing_hash, _updated_at) in canonicals_with_meta
        ],
    }

    hash_payload["listings"].sort(key=lambda x: x["canonical_id"])
    content_hash = _sha256_hex(_stable_json(hash_payload))

    key = f"{tenant_id}/{partner_id}/{destination}/feed.xml"
    uri = store.put_bytes(key=key, data=xml_bytes)

    snap = FeedSnapshot(
        tenant_id=tenant_id,
        partner_id=partner_id,
        destination=destination,
        storage_uri=uri,
        format=feed_format,
        content_hash=content_hash,
        listing_count=count,
        meta=meta,
        created_by="system",
        updated_by="system",
    )
    db.add(snap)
    await db.flush()
    return snap
