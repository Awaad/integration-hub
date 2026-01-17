from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.canonical.v1.listing import ListingCanonicalV1
from app.models.listing import Listing
from app.models.feed_snapshot import FeedSnapshot
from app.services.feed_generator import generate_xml_feed
from app.services.storage import LocalObjectStore

async def build_partner_feed_snapshot(
    db: AsyncSession,
    *,
    tenant_id: str,
    partner_id: str,
    destination: str,
    store: LocalObjectStore,
) -> FeedSnapshot:
    # For now: include active listings only
    rows = (await db.execute(
        select(Listing).where(
            Listing.tenant_id == tenant_id,
            Listing.partner_id == partner_id,
            Listing.schema == "canonical.listing",
            Listing.schema_version == "1.0",
        )
    )).scalars().all()

    canonical_listings = [ListingCanonicalV1.model_validate(r.payload) for r in rows]

    xml_bytes, content_hash, count = generate_xml_feed(canonical_listings)

    key = f"{tenant_id}/{partner_id}/{destination}/feed.xml"
    uri = store.put_bytes(key=key, data=xml_bytes)

    snap = FeedSnapshot(
        tenant_id=tenant_id,
        partner_id=partner_id,
        destination=destination,
        storage_uri=uri,
        format="xml",
        content_hash=content_hash,
        listing_count=count,
        meta={"generator": "xml_v1"},
        created_by="system",
        updated_by="system",
    )
    db.add(snap)
    await db.flush()
    return snap
