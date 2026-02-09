from __future__ import annotations
import csv
import hashlib
from io import StringIO
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.destinations.feeds.base import FeedBuildOutput
from app.destinations.registry import get_destination_connector
from app.canonical.v1.listing import ListingCanonicalV1
from app.models.listing import Listing
from app.models.agent_external_identity import AgentExternalIdentity
from app.services.listing_state import canonical_status, should_include_listing
from app.services.feed_stats import summarize_skips
from app.services.media_urls import partner_has_active_media_token, resolve_listing_media_urls_bulk     
    
   

_ALLOWED_VARIANTS = {"orig", "thumb", "medium", "large"}


# CSV injection hardening (Excel/Sheets formula injection mitigation)
# Prefix potentially-dangerous leading characters with a single quote.
_CSV_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _slug(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "-")


def _csv_safe(v: Any) -> Any:
    if v is None:
        return ""
    if not isinstance(v, str):
        return v
    s = v
    if s and s[0] in _CSV_DANGEROUS_PREFIXES:
        return "'" + s
    return s

def _join_urls(items: list[dict[str, Any]]) -> str:
    # Keep order stable
    return "|".join(str(i["url"]) for i in items if i.get("url"))


def _room_count_fields(can: ListingCanonicalV1) -> tuple[str, str, str]:
    """
    Returns (bedrooms, living_rooms, room_count_key e.g. "3+1").
    Empty strings if missing.
    """
    b = ""
    lr = ""
    rc = ""
    prop = getattr(can, "property", None)
    if prop:
        b_val = getattr(prop, "bedrooms", None)
        lr_val = getattr(prop, "living_rooms", None)
        if b_val is not None:
            b = str(b_val)
        if lr_val is not None:
            lr = str(lr_val)
        if b_val is not None and lr_val is not None:
            rc = f"{b_val}+{lr_val}"
    return b, lr, rc


def _canonical_media_urls(can: ListingCanonicalV1) -> tuple[str, str]:
    """
    Returns (images_urls, floorplan_urls) from canonical media list.
    """
    media = list(can.media or [])
    images = [m for m in media if (getattr(m, "type", None) == "image") and getattr(m, "url", None)]
    floorplans = [m for m in media if (getattr(m, "type", None) == "floorplan") and getattr(m, "url", None)]

    images_sorted = sorted(
        images,
        key=lambda m: (int(getattr(m, "order", 0) or 0), str(getattr(m, "id", "") or "")),
    )
    floorplans_sorted = sorted(
        floorplans,
        key=lambda m: (int(getattr(m, "order", 0) or 0), str(getattr(m, "id", "") or "")),
    )

    return (
        "|".join(str(m.url) for m in images_sorted),
        "|".join(str(m.url) for m in floorplans_sorted),
    )



class PartnerCSVFeedPlugin:
    destination = "partner_csv"
    format = "csv"

    async def build(self, *, db: AsyncSession, tenant_id: str, partner_id: str, config: dict[str, Any]) -> FeedBuildOutput:

        feed_cfg = config or {}

        use_hub_media = bool(feed_cfg.get("use_hub_media_urls"))
        hub_variant = (feed_cfg.get("hub_media_variant") or "large").strip().lower()
        if hub_variant not in _ALLOWED_VARIANTS:
            hub_variant = "large"

        connector = get_destination_connector(self.destination)
        policy = connector.capabilities().listing_inclusion_policy

        rows = (await db.execute(select(Listing).where(
            Listing.tenant_id == tenant_id,
            Listing.partner_id == partner_id,
            Listing.is_active.is_(True),
            Listing.schema == "canonical.listing",
            Listing.schema_version.in_(["1.0.0", "1.0"]),
        ))).scalars().all()

        skipped: list[dict[str, Any]] = []

        # Pre-check token availability once
        hub_media_available = False
        if use_hub_media:
            hub_media_available = await partner_has_active_media_token(
                db, tenant_id=tenant_id, partner_id=partner_id
            )

        # Bulk media lookup once 
        media_map: dict[str, list[dict[str, Any]]] = {}
        if use_hub_media and hub_media_available and rows:
            listing_ids = [r.id for r in rows if getattr(r, "id", None)]
            media_map = await resolve_listing_media_urls_bulk(
                db,
                tenant_id=tenant_id,
                partner_id=partner_id,
                listing_ids=listing_ids,
                expected_agent_id=None,
                variant=hub_variant,
            )

        # Bulk external agent ids (destination = "partner_csv")
        agent_ids = sorted({r.agent_id for r in rows if getattr(r, "agent_id", None)})
        ext_agent_by_agent: dict[str, str] = {}
        if agent_ids:
            ext_rows = (
                await db.execute(
                    select(
                        AgentExternalIdentity.agent_id,
                        AgentExternalIdentity.external_agent_id,
                    ).where(
                        AgentExternalIdentity.tenant_id == tenant_id,
                        AgentExternalIdentity.partner_id == partner_id,
                        AgentExternalIdentity.destination == self.destination,
                        AgentExternalIdentity.is_active.is_(True),
                        AgentExternalIdentity.agent_id.in_(agent_ids),
                    )
                )
            ).all()
            ext_agent_by_agent = {aid: ext for (aid, ext) in ext_rows}

        buf = StringIO()
        w = csv.writer(buf)
    
        # Header depends on policy
        header = [
            "listing_id",
            "agent_id",
            "external_agent_id",
            "title",
            "price_amount",
            "currency",
            "property_type",
            "title_type",
            "country_code",
            "state",
            "city",
            "area",
            "geo_key",
            "bedrooms",
            "living_rooms",
            "room_count",
            "image_urls",
            "floorplan_urls",
        ]

        if policy == "include_with_status":
            header.append("status")
        w.writerow(header)

        count = 0
        
        hub_media_used = 0  # at least one image/floorplan emitted from hub
        hub_media_no_listing_media = 0  # listing had no listing_media links (no rows in map)
        hub_media_no_supported_types = 0  # listing_media exists, but no image/floorplan among them
        hub_media_disabled_or_unavailable = 0  # hub media not attempted (flag off or no token)
        hub_media_partial_fallback = 0  # hub provided one type but not the other (image vs floorplan)

        missing_ext_agent = 0  # agent_id present but no matching ext agent id found
       
        for r in rows:
            status = canonical_status(r.payload)

            # Exclude inactive if policy says so
            if not should_include_listing(policy=policy, status=status):
                skipped.append({"listing_id": str(r.id), "reason": "policy_excluded", "detail": f"status={status}"})
                continue

            can = ListingCanonicalV1.model_validate(r.payload)

            price = can.list_price.amount if can.list_price else ""
            cur = can.list_price.currency if can.list_price else ""

            prop_type = ""
            title_type = ""
            prop = getattr(can, "property", None)
            if prop:
                prop_type = str(getattr(prop, "property_type", "") or "")
                title_type = str(getattr(prop, "title_type", "") or "")

            addr = getattr(can, "address", None)
            country_code = str(getattr(addr, "country_code", "") or "") if addr else ""
            state = str(getattr(addr, "state", "") or "") if addr else ""
            city = str(getattr(addr, "city", "") or "") if addr else ""
            area = str(getattr(addr, "area", "") or "") if addr else ""

            geo_key = f"{_slug(city)}:{_slug(area)}" if city or area else ":"

            bedrooms, living_rooms, room_count = _room_count_fields(can)

            # external agent id is optional, but if agent_id is present and no ext agent id found, count it as missing. could be a misconfiguration
            agent_id = getattr(r, "agent_id", "") or ""
            ext_agent_id = ""
            if agent_id:
                ext_agent_id = ext_agent_by_agent.get(r.agent_id) or ""
                if not ext_agent_id:
                    missing_ext_agent += 1

            image_urls = ""
            floorplan_urls = ""

            attempted_hub = bool(use_hub_media and hub_media_available)

            # compute canonical once (used both for fallback + partial stats)
            canon_imgs, canon_fps = _canonical_media_urls(can)
            canon_has_img = bool(canon_imgs)
            canon_has_fp = bool(canon_fps)

            # per-listing hub flags
            hub_has_img = False
            hub_has_fp = False

            if attempted_hub:
                items = media_map.get(r.id) or []
                if not items:
                    hub_media_no_listing_media += 1
                else:
                    img_items = [mi for mi in items if (mi.get("type") or "") == "image"]
                    fp_items = [mi for mi in items if (mi.get("type") or "") == "floorplan"]

                    hub_has_img = bool(img_items)
                    hub_has_fp = bool(fp_items)

                    if not img_items and not fp_items:
                        hub_media_no_supported_types += 1
                    else:
                        # We will emit what we have, and fallback per-type
                        if hub_has_img:
                            image_urls = _join_urls(img_items)
                        if hub_has_fp:
                            floorplan_urls = _join_urls(fp_items)

                        hub_media_used += 1

                        # partial fallback: hub had one type but not the other,
                        # AND canonical actually had the missing type
                        if (hub_has_img and not hub_has_fp and canon_has_fp) or (hub_has_fp and not hub_has_img and canon_has_img):
                            hub_media_partial_fallback += 1

            else:
                hub_media_disabled_or_unavailable += 1

            # Fallback per-type to canonical
            if not image_urls:
                image_urls = canon_imgs
            if not floorplan_urls:
                floorplan_urls = canon_fps


            out_row = [
                _csv_safe(can.canonical_id),
                _csv_safe(agent_id),
                _csv_safe(ext_agent_id),
                _csv_safe(can.title or ""),
                _csv_safe(price),
                _csv_safe(cur),
                _csv_safe(prop_type),
                _csv_safe(title_type),
                _csv_safe(country_code),
                _csv_safe(state),
                _csv_safe(city),
                _csv_safe(area),
                _csv_safe(geo_key),
                _csv_safe(bedrooms),
                _csv_safe(living_rooms),
                _csv_safe(room_count),
                _csv_safe(image_urls),
                _csv_safe(floorplan_urls),
            ]

            if policy == "include_with_status":
                out_row.append(_csv_safe(status))

            w.writerow(out_row)
            count += 1

        data = buf.getvalue().encode("utf-8")
        h = hashlib.sha256(data).hexdigest()

        skipped_by_reason = summarize_skips(skipped)

        hub_media_fallback = (
            hub_media_no_listing_media + hub_media_no_supported_types + hub_media_partial_fallback
        )

        meta: dict[str, Any] = {
            "generator": "partner_csv_v1",
            "listing_inclusion_policy": policy,
            "skipped_count": int(sum(skipped_by_reason.values())),
            "skipped_by_reason": dict(skipped_by_reason),
            "hub_media_enabled": bool(use_hub_media),
            "hub_media_available": bool(hub_media_available) if use_hub_media else None,
            "hub_media_variant": hub_variant if use_hub_media else None,
            "hub_media_used": hub_media_used,
            "hub_media_fallback": hub_media_fallback,
            "missing_external_agent_id": missing_ext_agent,
            "hub_media_no_listing_media": hub_media_no_listing_media,
            "hub_media_no_supported_types": hub_media_no_supported_types,
            "hub_media_partial_fallback": hub_media_partial_fallback,
            "hub_media_disabled_or_unavailable": hub_media_disabled_or_unavailable,
        }
        meta["skipped"] = skipped[:200]

        return FeedBuildOutput(
            format="csv",
            bytes=data,
            listing_count=count,
            content_hash=h,
            meta=meta,
        )
