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
                agent_id=None,  # partner-wide feed
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
             "city",
             "bedrooms",
             "living_rooms",
             "room_count",
             "media_urls",
        ]
        if policy == "include_with_status":
            header.append("status")
        w.writerow(header)

        count = 0
        hub_media_used = 0
        hub_media_fallback = 0
        missing_ext_agent = 0

        for r in rows:
            status = canonical_status(r.payload)

            # Exclude inactive if policy says so
            if not should_include_listing(policy=policy, status=status):
                skipped.append({"listing_id": str(r.id), "reason": "policy_excluded", "detail": f"status={status}"})
                continue

            can = ListingCanonicalV1.model_validate(r.payload)
            price = can.list_price.amount if can.list_price else ""
            cur = can.list_price.currency if can.list_price else ""
            city = can.address.city if can.address else ""

            bedrooms, living_rooms, room_count = _room_count_fields(can)

            # external agent id is optional, but if agent_id is present and no ext agent id found, count it as missing. could be a misconfiguration
            ext_agent_id = ""
            if getattr(r, "agent_id", None):
                ext_agent_id = ext_agent_by_agent.get(r.agent_id) or ""
                if not ext_agent_id:
                    missing_ext_agent += 1

            media_urls = ""
            if use_hub_media and hub_media_available:
                items = media_map.get(r.id) or []
                
                img_items = [mi for mi in items if (mi.get("type") or "") == "image"]
                if img_items:
                    hub_media_used += 1
                    media_urls = _join_urls(img_items)
                else:
                    hub_media_fallback += 1
            # fallback: use canonical media urls if hub not present
            if not media_urls:
                img = [m for m in (can.media or []) if m.type == "image" and getattr(m, "url", None)]
                img_sorted = sorted(img, key=lambda m: (int(getattr(m, "order", 0) or 0), str(getattr(m, "id", "") or "")))
                media_urls = "|".join(str(m.url) for m in img_sorted)

            out_row = [
                can.canonical_id,
                getattr(r, "agent_id", "") or "",
                ext_agent_id,
                can.title or "",
                price,
                cur,
                city,
                bedrooms,
                living_rooms,
                room_count,
                media_urls,
            ]
            if policy == "include_with_status":
                out_row.append(status)

            w.writerow(out_row)
            count += 1

        data = buf.getvalue().encode("utf-8")
        h = hashlib.sha256(data).hexdigest()

        skipped_by_reason = summarize_skips(skipped)

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
        }
        meta["skipped"] = skipped[:200]

        return FeedBuildOutput(
            format="csv",
            bytes=data,
            listing_count=count,
            content_hash=h,
            meta=meta,
        )
