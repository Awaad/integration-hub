from __future__ import annotations

import hashlib
from typing import Any
import xml.etree.ElementTree as ET

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.feed_stats import Timer, summarize_warnings, summarize_skips
from app.canonical.v1.listing import ListingCanonicalV1
from app.models.listing import Listing
from app.models.agent_external_identity import AgentExternalIdentity
from app.models.destination_enum_mapping import DestinationEnumMapping
from app.models.destination_geo_mapping import DestinationGeoMapping
from app.models.geo_country import GeoCountry
from app.models.geo_city import GeoCity
from app.models.geo_area import GeoArea
from app.models.partner_public_token import PartnerPublicToken
from app.services.feeds.evler101_xml import build_101evler_xml, Evler101Ad
from app.services.listing_state import canonical_status, should_include_listing
from app.services.media_urls import resolve_listing_media_urls
from app.destinations.feeds.base import FeedBuildOutput
from app.destinations.evler101.ad_projection import project_ad_fields
from app.destinations.registry import get_destination_connector


_ALLOWED_VARIANTS = {"orig", "thumb", "medium", "large"}


def _slug(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "-")


async def _enum(db: AsyncSession, *, ns: str, key: str) -> str | None:
    return (
        await db.execute(
            select(DestinationEnumMapping.destination_value).where(
                DestinationEnumMapping.destination == "101evler",
                DestinationEnumMapping.namespace == ns,
                DestinationEnumMapping.source_key == key,
            )
        )
    ).scalar_one_or_none()


async def _area_id_for_101evler(db: AsyncSession, *, country_code: str, city_slug: str, area_slug: str) -> str | None:
    """
    Single-query geo lookup:
      GeoCountry(code) -> GeoCity(slug) -> GeoArea(slug) -> DestinationGeoMapping(destination_area_id)
    """
    if not country_code or not city_slug or not area_slug:
        return None

    return (
        await db.execute(
            select(DestinationGeoMapping.destination_area_id)
            .select_from(DestinationGeoMapping)
            .join(GeoArea, GeoArea.id == DestinationGeoMapping.geo_area_id)
            .join(GeoCity, GeoCity.id == GeoArea.city_id)
            .join(GeoCountry, GeoCountry.id == GeoCity.country_id)
            .where(
                DestinationGeoMapping.destination == "101evler",
                GeoCountry.code == country_code,
                GeoCity.slug == city_slug,
                GeoArea.slug == area_slug,
            )
        )
    ).scalar_one_or_none()


class Evler101FeedPlugin:
    destination = "101evler"
    format = "xml"

    async def build(self, *, db: AsyncSession, tenant_id: str, partner_id: str, config: dict[str, Any]) -> FeedBuildOutput:
        feed_cfg = config or {}
        use_hub_media = bool(feed_cfg.get("use_hub_media_urls"))

        hub_variant = (feed_cfg.get("hub_media_variant") or "large").strip().lower()
        if hub_variant not in _ALLOWED_VARIANTS:
            hub_variant = "large"

        connector = get_destination_connector(self.destination)
        policy = connector.capabilities().listing_inclusion_policy

        # Pre-check whether partner has an active media token
        hub_media_available = False
        if use_hub_media:
            hub_media_available = bool(
                (
                    await db.execute(
                        select(PartnerPublicToken.id)
                        .where(
                            PartnerPublicToken.tenant_id == tenant_id,
                            PartnerPublicToken.partner_id == partner_id,
                            PartnerPublicToken.scope == "media",
                            PartnerPublicToken.is_active.is_(True),
                        )
                        .limit(1)
                    )
                ).scalar_one_or_none()
            )

        rows = (
            await db.execute(
                select(Listing).where(
                    Listing.tenant_id == tenant_id,
                    Listing.partner_id == partner_id,
                    Listing.is_active.is_(True),
                    Listing.schema == "canonical.listing",
                    Listing.schema_version.in_(["1.0.0", "1.0"]),
                )
            )
        ).scalars().all()

        warnings: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        ads: list[Evler101Ad] = []

        # preload + in-memory caches for whole build
        agent_ids = sorted({r.agent_id for r in rows if getattr(r, "agent_id", None)})
        realtor_by_agent: dict[str, str] = {}
        if agent_ids:
            realtor_rows = (
                await db.execute(
                    select(AgentExternalIdentity.agent_id, AgentExternalIdentity.external_agent_id).where(
                        AgentExternalIdentity.tenant_id == tenant_id,
                        AgentExternalIdentity.partner_id == partner_id,
                        AgentExternalIdentity.destination == "101evler",
                        AgentExternalIdentity.is_active.is_(True),
                        AgentExternalIdentity.agent_id.in_(agent_ids),
                    )
                )
            ).all()
            realtor_by_agent = {aid: ext for (aid, ext) in realtor_rows}

        # Cache for enum mappings (ns,key)->destination_value
        enum_cache: dict[tuple[str, str], str | None] = {}

        async def enum_cached(ns: str, key: Any) -> str | None:
            ns = (ns or "").strip().lower()

            if key is None:
                return None
            key_s = str(key)
            if not key_s:
                return None
            k = (ns, key_s)
            if k in enum_cache:
                return enum_cache[k]
            v = await _enum(db, ns=ns, key=key_s)
            enum_cache[k] = v
            return v

        # Cache for area mapping (country, city_slug, area_slug)->area_id
        area_cache: dict[tuple[str, str, str], str | None] = {}

        async def area_cached(country_code: str, city_slug: str, area_slug: str) -> str | None:
            if not city_slug or not area_slug:
                return None
            k = (country_code, city_slug, area_slug)
            if k in area_cache:
                return area_cache[k]
            v = await _area_id_for_101evler(db, country_code=country_code, city_slug=city_slug, area_slug=area_slug)
            area_cache[k] = v
            return v
        

        hub_media_used = 0
        hub_media_fallback = 0

        for r in rows:
            status = canonical_status(r.payload)
            if not should_include_listing(policy=policy, status=status):
                skipped.append(
                    {
                        "listing_id": str(getattr(r, "id", "")) or str((r.payload or {}).get("canonical_id") or ""),
                        "reason": "policy_excluded",
                        "detail": f"status={status}",
                    }
                )
                continue

            can = ListingCanonicalV1.model_validate(r.payload)

            prop_type = getattr(can.property, "property_type", None) if can.property else None
            type_id = await enum_cached("property_type", prop_type)
            if not type_id:
                warnings.append(
                    {
                        "listing_id": can.canonical_id,
                        "code": "MISSING_TYPE_ID",
                        "message": f"Unmapped property_type={prop_type}",
                    }
                )
                skipped.append(
                    {
                        "listing_id": can.canonical_id,
                        "reason": "missing_mapping",
                        "detail": f"property_type={prop_type}",
                    }
                )
                continue

            if not can.list_price:
                warnings.append({"listing_id": can.canonical_id, "code": "MISSING_PRICE", "message": "Missing list_price"})
                skipped.append({"listing_id": can.canonical_id, "reason": "missing_required", "detail": "list_price"})
                continue

            currency_id = await enum_cached("currency", can.list_price.currency)
            if not currency_id:
                warnings.append(
                    {
                        "listing_id": can.canonical_id,
                        "code": "MISSING_CURRENCY",
                        "message": f"Unmapped currency={can.list_price.currency}",
                    }
                )
                skipped.append(
                    {
                        "listing_id": can.canonical_id,
                        "reason": "missing_mapping",
                        "detail": f"currency={can.list_price.currency}",
                    }
                )
                continue

            city_slug = _slug(can.address.city) if can.address else ""
            area_slug = _slug(getattr(can.address, "area", None) or "") if can.address else ""
            area_id = await area_cached("NCY", city_slug, area_slug)
            if not area_id:
                warnings.append(
                    {
                        "listing_id": can.canonical_id,
                        "code": "MISSING_AREA_ID",
                        "message": f"Unmapped geo {city_slug}:{area_slug}",
                    }
                )
                skipped.append(
                    {
                        "listing_id": can.canonical_id,
                        "reason": "missing_geo_mapping",
                        "detail": f"{city_slug}:{area_slug}",
                    }
                )
                continue

            agent_id = getattr(r, "agent_id", None)
            realtor_id = realtor_by_agent.get(agent_id) if agent_id else None

            room_count_key = None
            if can.property:
                b = getattr(can.property, "bedrooms", None)
                lr = getattr(can.property, "living_rooms", None)
                if b is not None and lr is not None:
                    room_count_key = f"{b}+{lr}"
            room_count_id = await enum_cached("rooms", room_count_key)

            title_type_key = getattr(getattr(can, "property", None), "title_type", None)
            title_type_id = await enum_cached("title_type", title_type_key)

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

            pics: list[dict[str, Any]] = []

            if use_hub_media and hub_media_available:
                media_items = await resolve_listing_media_urls(
                    db,
                    tenant_id=tenant_id,
                    partner_id=partner_id,
                    agent_id=r.agent_id,  # enforce agent isolation
                    listing_id=r.id,
                    variant=hub_variant,
                )

                if media_items:
                    img_items = [mi for mi in media_items if (mi.get("type") or "") == "image"]
                    if img_items:
                        hub_media_used += 1

                        img_items_sorted = sorted(
                            img_items,
                            key=lambda mi: (
                                0 if mi.get("is_primary") else 1,
                                int(mi.get("order") or 0),
                                str(mi.get("media_id") or ""),
                            ),
                        )

                        for idx, mi in enumerate(img_items_sorted, start=1):
                            pics.append({"picture_url": str(mi["url"]), "order_by": idx})

                        ads.append(Evler101Ad(listing_id=can.canonical_id, fields=fields, pictures=pics))
                        continue

                    hub_media_fallback += 1
                else:
                    hub_media_fallback += 1

            images = [m for m in (can.media or []) if m.type == "image"]
            images_sorted = sorted(images, key=lambda m: (int(getattr(m, "order", 0) or 0), str(getattr(m, "id", "") or "")))
            for idx, m in enumerate(images_sorted, start=1):
                pic = {"picture_url": str(m.url), "order_by": idx}
                mmeta = getattr(m, "metadata", None) or {}
                if isinstance(mmeta, dict) and mmeta.get("group_id") is not None:
                    pic["group_id"] = mmeta["group_id"]
                pics.append(pic)

            ads.append(Evler101Ad(listing_id=can.canonical_id, fields=fields, pictures=pics))

        xml_bytes, _builder_warnings, count = build_101evler_xml(ads=ads)
        h = hashlib.sha256(xml_bytes).hexdigest()

        parse_ok = True
        with Timer() as t:
            try:
                ET.fromstring(xml_bytes)
            except Exception:
                parse_ok = False
        parse_ms = t.ms

        warnings_by_code = summarize_warnings(warnings)
        skipped_by_reason = summarize_skips(skipped)

        meta: dict[str, Any] = {
            "generator": "evler101_feed_v1",
            "listing_inclusion_policy": policy,
            "warnings_count": int(sum(warnings_by_code.values())),
            "warnings_by_code": dict(warnings_by_code),
            "skipped_count": int(sum(skipped_by_reason.values())),
            "skipped_by_reason": dict(skipped_by_reason),
            "parse_ok": parse_ok,
            "parse_ms": parse_ms,
            "hub_media_used": hub_media_used,
            "hub_media_fallback": hub_media_fallback,
            "hub_media_enabled": bool(use_hub_media),
            "hub_media_variant": hub_variant if use_hub_media else None,
            "hub_media_available": bool(hub_media_available) if use_hub_media else None,
        }

        meta["warnings"] = warnings[:200]
        meta["skipped"] = skipped[:200]

        return FeedBuildOutput(
            format="xml",
            bytes=xml_bytes,
            listing_count=count,
            meta=meta,
            content_hash=h,
        )
