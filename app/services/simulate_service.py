from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.listing import Listing
from app.models.listing_external_mapping import ListingExternalMapping
from app.services.publish_service import build_projected_payload_from_parts  

async def build_projected_payload_for_listing(
    db: AsyncSession, *, tenant_id: str, partner_id: str, destination: str, listing_id: str
) -> tuple[dict, str | None]:
    listing = (await db.execute(select(Listing).where(
        Listing.id == listing_id,
        Listing.tenant_id == tenant_id,
        Listing.partner_id == partner_id,
    ))).scalar_oneor_none()

    if not listing:
        raise ValueError("listing_not_found")

    mapping = (await db.execute(select(ListingExternalMapping).where(
        ListingExternalMapping.tenant_id == tenant_id,
        ListingExternalMapping.destination == destination,
        ListingExternalMapping.listing_id == listing_id,
    ))).scalar_one_or_none()

    projected, external_listing_id = await build_projected_payload_from_parts(
        db,
        tenant_id=tenant_id,
        partner_id=partner_id,
        agent_id=listing.agent_id,
        destination=destination,
        listing_id=listing_id,
    )

    # external_listing_id should match mapping.external_listing_id; prefer the computed one:
    return projected, external_listing_id, listing.agent_id