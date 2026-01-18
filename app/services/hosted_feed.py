from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feed_snapshot import FeedSnapshot

from app.services.storage import LocalObjectStore
from app.models.partner_destination_setting import PartnerDestinationSetting

from app.destinations.feeds.registry import get_feed_plugin



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

    plugin = get_feed_plugin(dest)
    out = await plugin.build(
        db=db,
        tenant_id=tenant_id,
        partner_id=partner_id,
        config=setting.config or {},
    )

    key = f"{tenant_id}/{partner_id}/{dest}/feed.{out.format}"
    uri = store.put_bytes(key=key, data=out.bytes)

    snap = FeedSnapshot(
        tenant_id=tenant_id,
        partner_id=partner_id,
        destination=dest,
        storage_uri=uri,
        format=out.format,
        content_hash=out.content_hash,
        listing_count=out.listing_count,
        meta=out.meta,
        created_by="system",
        updated_by="system",
    )
    db.add(snap)
    await db.flush()
    return snap
