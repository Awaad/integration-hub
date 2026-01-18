from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.canonical.v1.listing import ListingCanonicalV1
from app.models.delivery import Delivery
from app.models.listing import Listing
from app.models.agent_external_identity import AgentExternalIdentity
from app.models.listing_external_mapping import ListingExternalMapping
from app.destinations.registry import get_destination_connector
from app.projections.registry import get_projector
from app.projections.base import ProjectionContext

async def build_projected_payload(
    db: AsyncSession,
    *,
    delivery: Delivery,
) -> tuple[dict, str | None]:
    listing = (await db.execute(select(Listing).where(Listing.id == delivery.listing_id))).scalar_one()

    canonical = ListingCanonicalV1.model_validate(listing.payload)

    mapping = (await db.execute(
        select(ListingExternalMapping).where(
            ListingExternalMapping.tenant_id == delivery.tenant_id,
            ListingExternalMapping.destination == delivery.destination,
            ListingExternalMapping.listing_id == listing.id,
        )
    )).scalar_one_or_none()

    ext_agent = (await db.execute(
        select(AgentExternalIdentity).where(
            AgentExternalIdentity.tenant_id == delivery.tenant_id,
            AgentExternalIdentity.partner_id == delivery.partner_id,
            AgentExternalIdentity.agent_id == delivery.agent_id,
            AgentExternalIdentity.destination == delivery.destination,
            AgentExternalIdentity.is_active.is_(True),
        )
    )).scalar_one_or_none()

    projector = get_projector(delivery.destination)

    projected = projector.project_listing(
        canonical=canonical,
        ctx=ProjectionContext(
            tenant_id=delivery.tenant_id,
            partner_id=delivery.partner_id,
            agent_id=delivery.agent_id,
            destination=delivery.destination,
            external_agent_id=ext_agent.external_agent_id if ext_agent else None,
            external_listing_id=mapping.external_listing_id if mapping else None,
        )
    )

    return projected, (mapping.external_listing_id if mapping else None)

async def publish_projected_payload(
    *,
    destination: str,
    payload: dict,
    credentials: dict,
):
    connector = get_destination_connector(destination)
    caps = connector.capabilities()

    if caps.transport == "pull_only":
        return await connector.publish_listing(payload=payload, credentials=credentials)  # likely NOT_SUPPORTED

    if caps.transport == "hosted_feed":
        # Hosted feed: publishing is not per listing; it’s snapshot generation.
        # We'll return a synthetic success and let Phase 5.2 optimize to batch snapshots.
        return await connector.publish_listing(payload=payload, credentials=credentials)

    # push_api
    return await connector.publish_listing(payload=payload, credentials=credentials)
