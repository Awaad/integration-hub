from __future__ import annotations

from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import AdapterContext
from app.adapters.registry import get_adapter
from app.core.ids import gen_id
from app.models.source_listing_mapping import SourceListingMapping
from app.models.listing import Listing
from app.services.canonical_validate import validate_and_normalize_canonical


class IngestError(Exception):
    def __init__(self, status_code: int, detail: Any):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


async def ingest_listing(
    *,
    db: AsyncSession,
    tenant_id: str,
    partner_id: str,
    agent_id: str,
    partner_key: str,
    source_listing_id: str,
    partner_payload: dict[str, Any],
) -> tuple[Listing, bool]:
    """
    Returns (listing, material_change).
    - material_change=True when content_hash changed (new outbox event is warranted).
    """
    partner_key_norm = partner_key.lower().strip()

    mapping = (await db.execute(
        select(SourceListingMapping).where(
            SourceListingMapping.tenant_id == tenant_id,
            SourceListingMapping.partner_id == partner_id,
            SourceListingMapping.partner_key == partner_key_norm,
            SourceListingMapping.source_listing_id == source_listing_id,
        )
    )).scalar_one_or_none()

    # Determine hub listing_id
    if mapping:
        listing_id = mapping.listing_id
    else:
        listing_id = gen_id("lst")

    # Adapter mapping -> canonical dict
    adapter = get_adapter(partner_key_norm)
    ctx = AdapterContext(
        tenant_id=tenant_id,
        partner_id=partner_id,
        agent_id=agent_id,
        source_listing_id=source_listing_id,
    )
    mapped = adapter.map_listing(payload=partner_payload, ctx=ctx)
    if not mapped.ok or not mapped.canonical:
        raise IngestError(422, {"errors": mapped.errors})

    canonical_payload = dict(mapped.canonical)
    canonical_payload["schema"] = "canonical.listing"
    canonical_payload["schema_version"] = "1.0"
    canonical_payload["canonical_id"] = listing_id
    canonical_payload["source_listing_id"] = source_listing_id

    # Validate + normalize + hash 
    res = validate_and_normalize_canonical(
        schema="canonical.listing",
        schema_version="1.0",
        payload=canonical_payload,
    )
    if not res.ok or not res.normalized or not res.content_hash:
        raise IngestError(422, {"errors": res.errors})

    # Upsert listing row
    listing = (await db.execute(select(Listing).where(
        Listing.id == listing_id,
        Listing.tenant_id == tenant_id,
        Listing.partner_id == partner_id,
        Listing.agent_id == agent_id,
    ))).scalar_one_or_none()

    material_change = False

    if not listing:
        listing = Listing(
            id=listing_id,
            tenant_id=tenant_id,
            partner_id=partner_id,
            agent_id=agent_id,
            schema="canonical.listing",
            schema_version="1.0",
            payload=res.normalized,
            content_hash=res.content_hash,
            status=res.normalized.get("status", "draft"),
            created_by="ingest",
            updated_by="ingest",
        )
        db.add(listing)
        material_change = True
    else:
        # material change = hash changed
        if listing.content_hash != res.content_hash:
            material_change = True
            listing.payload = res.normalized
            listing.content_hash = res.content_hash
            listing.status = res.normalized.get("status", listing.status)
            listing.updated_by = "ingest"
            listing.schema = "canonical.listing"
            listing.schema_version = "1.0"

    # Upsert mapping if missing
    if not mapping:
        mapping = SourceListingMapping(
            tenant_id=tenant_id,
            partner_id=partner_id,
            agent_id=agent_id,
            partner_key=partner_key_norm,
            source_listing_id=source_listing_id,
            listing_id=listing_id,
        )
        db.add(mapping)

    await db.flush()
    return listing, material_change
