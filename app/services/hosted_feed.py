from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.canonical.v1.listing import ListingCanonicalV1
from app.models.listing import Listing
from app.models.feed_snapshot import FeedSnapshot
from app.services.feed_generator import generate_xml_feed
from app.services.storage import LocalObjectStore
from app.models.partner_destination_setting import PartnerDestinationSetting
from app.services.feeds.evler101_xml import build_101evler_xml


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

    pairs = [(ListingCanonicalV1.model_validate(r.payload), r.updated_at) for r in rows]

    if destination == "101evler":
        xml_bytes, warnings, count = build_101evler_xml(listings=pairs, config=cfg)
        feed_format = "xml"
        meta = {"generator": "101evler_xml_v1", "warnings": [w.__dict__ for w in warnings]}
    else:
        # fallback generic feed 
        xml_bytes, content_hash, count = generate_xml_feed([p[0] for p in pairs])
        warnings = []
        feed_format = "xml"
        meta = {"generator": "xml_v1"}

    # compute content hash from bytes
    import hashlib
    content_hash = hashlib.sha256(xml_bytes).hexdigest()

    # store file key includes destination
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
