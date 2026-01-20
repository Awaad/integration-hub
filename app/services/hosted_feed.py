from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feed_snapshot import FeedSnapshot
from app.models.listing import Listing
from app.services.storage import LocalObjectStore
from app.models.partner_destination_setting import PartnerDestinationSetting

from app.services.feed_hashes import hash_config, hash_listing_inputs, hash_fingerprint
from app.destinations.feeds.registry import get_feed_plugin
from app.services.gzip_util import gzip_bytes


def _clean_config_for_fingerprint(cfg: dict) -> dict:
    """
    Remove ephemeral/secret fields that should NOT trigger a rebuild.
    """
    out = dict(cfg or {})
    out.pop("feed_token", None)
    return out


async def build_partner_feed_snapshot(
    db: AsyncSession,
    *,
    tenant_id: str,
    partner_id: str,
    destination: str,
    store: LocalObjectStore,
) -> FeedSnapshot:
    dest = destination.lower().strip()

    setting = (await db.execute(select(PartnerDestinationSetting).where(
        PartnerDestinationSetting.tenant_id == tenant_id,
        PartnerDestinationSetting.partner_id == partner_id,
        PartnerDestinationSetting.destination == dest,
    ))).scalar_one()

    cfg_for_fp = _clean_config_for_fingerprint(setting.config or {})

    # Cheap fingerprint inputs: listing ids + listing content hashes
    rows = (
        await db.execute(
            select(Listing.id, Listing.content_hash).where(
                Listing.tenant_id == tenant_id,
                Listing.partner_id == partner_id,
                Listing.schema == "canonical.listing",
                Listing.schema_version == "1.0",
            ).order_by(Listing.id.asc())
        )
    ).all()

    listing_summaries = [{"id": str(rid), "hash": (ch or "")} for (rid, ch) in rows]
    config_hash = hash_config(cfg_for_fp)
    input_hash = hash_listing_inputs(listing_summaries)
    fingerprint = hash_fingerprint(destination=dest, config_hash=config_hash, input_hash=input_hash)

    # Load latest snapshot for this partner+destination
    latest = (
        await db.execute(
            select(FeedSnapshot).where(
                FeedSnapshot.tenant_id == tenant_id,
                FeedSnapshot.partner_id == partner_id,
                FeedSnapshot.destination == dest,
            ).order_by(desc(FeedSnapshot.created_at)).limit(1)
        )
    ).scalar_one_or_none()

    latest_fp = None
    if latest and isinstance(latest.meta, dict):
        latest_fp = latest.meta.get("fingerprint")

    if latest and latest_fp == fingerprint:
        # no-op: nothing changed (by our fingerprint definition)
        return latest

    # Build a new feed via destination plugin
    plugin = get_feed_plugin(dest)
    out = await plugin.build(
        db=db,
        tenant_id=tenant_id,
        partner_id=partner_id,
        config=setting.config or {},
    )

    key = f"{tenant_id}/{partner_id}/{dest}/feed.{out.format}"
    uri = store.put_bytes(key=key, data=out.bytes)

    gz_key = f"{tenant_id}/{partner_id}/{dest}/feed.{out.format}.gz"
    gz_data = gzip_bytes(out.bytes)
    gz_uri = store.put_bytes(key=gz_key, data=gz_data)

    meta = dict(out.meta or {})
    meta["fingerprint"] = fingerprint
    meta["config_hash"] = config_hash
    meta["input_hash"] = input_hash
    meta["built_at"] = datetime.now(timezone.utc).isoformat()
    meta["listing_count"] = out.listing_count
    meta["gzip_available"] = True
    
    snap = FeedSnapshot(
        tenant_id=tenant_id,
        partner_id=partner_id,
        destination=dest,
        storage_uri=uri,
        gzip_storage_uri=gz_uri,
        gzip_size_bytes=len(gz_data),
        format=out.format,
        content_hash=out.content_hash,
        listing_count=out.listing_count,
        meta=meta,
        created_by="system",
        updated_by="system",
    )
    db.add(snap)
    await db.flush()
    return snap
