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



async def _project_listing(
    db: AsyncSession,
    *,
    tenant_id: str,
    partner_id: str,
    agent_id: str,
    destination: str,
    listing_id: str,
) -> tuple[dict, str | None]:
    listing = (await db.execute(select(Listing).where(Listing.id == listing_id))).scalar_one()

    canonical = ListingCanonicalV1.model_validate(listing.payload)

    mapping = (await db.execute(
        select(ListingExternalMapping).where(
            ListingExternalMapping.tenant_id == tenant_id,
            ListingExternalMapping.destination == destination,
            ListingExternalMapping.listing_id == listing.id,
        )
    )).scalar_one_or_none()

    ext_agent = (await db.execute(
        select(AgentExternalIdentity).where(
            AgentExternalIdentity.tenant_id == tenant_id,
            AgentExternalIdentity.partner_id == partner_id,
            AgentExternalIdentity.agent_id == agent_id,
            AgentExternalIdentity.destination == destination,
            AgentExternalIdentity.is_active.is_(True),
        )
    )).scalar_one_or_none()

    projector = get_projector(destination)

    projected = projector.project_listing(
        canonical=canonical,
        ctx=ProjectionContext(
            tenant_id=tenant_id,
            partner_id=partner_id,
            agent_id=agent_id,
            destination=destination,
            external_agent_id=ext_agent.external_agent_id if ext_agent else None,
            external_listing_id=mapping.external_listing_id if mapping else None,
        )
    )

    return projected, (mapping.external_listing_id if mapping else None)


async def build_projected_payload(
    db: AsyncSession,
    *,
    delivery: "Delivery",
) -> tuple[dict, str | None]:
    return await _project_listing(
        db,
        tenant_id=delivery.tenant_id,
        partner_id=delivery.partner_id,
        agent_id=delivery.agent_id,
        destination=delivery.destination,
        listing_id=delivery.listing_id,
    )


async def build_projected_payload_from_parts(
    db: AsyncSession,
    *,
    tenant_id: str,
    partner_id: str,
    agent_id: str,
    destination: str,
    listing_id: str,
) -> tuple[dict, str | None]:
    return await _project_listing(
        db,
        tenant_id=tenant_id,
        partner_id=partner_id,
        agent_id=agent_id,
        destination=destination,
        listing_id=listing_id,
    )



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
