from __future__ import annotations
from app.canonical.v1 import listing
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.canonical.v1.listing import ListingCanonicalV1
from app.canonical.registry import resolve_schema
from app.models.delivery import Delivery
from app.models.listing import Listing
from app.models.agent_external_identity import AgentExternalIdentity
from app.models.listing_external_mapping import ListingExternalMapping
from app.models.partner_destination_setting import PartnerDestinationSetting
from app.destinations.registry import get_destination_connector
from app.projections.registry import get_projector
from app.projections.base import ProjectionContext
from app.services.destination_config import destination_mode
from app.services.media_urls import resolve_listing_media_urls



_ALLOWED_VARIANTS = {"orig", "thumb", "medium", "large"}

async def _project_listing(
    db: AsyncSession,
    *,
    tenant_id: str,
    partner_id: str,
    agent_id: str | None,
    destination: str,
    listing_id: str,
) -> tuple[dict, str | None]:
    
    dest = (destination or "").lower().strip()

    # Destination config (gate hub media, choose variant)
    setting = (
        await db.execute(
            select(PartnerDestinationSetting).where(
                PartnerDestinationSetting.tenant_id == tenant_id,
                PartnerDestinationSetting.partner_id == partner_id,
                PartnerDestinationSetting.destination == dest,
                PartnerDestinationSetting.is_enabled.is_(True),
            )
        )
    ).scalar_one_or_none()
    cfg = (setting.config or {}) if setting else {}

    use_hub_media = bool(cfg.get("use_hub_media_urls"))
    hub_variant = (cfg.get("hub_media_variant") or "large").strip().lower()
    if hub_variant not in _ALLOWED_VARIANTS:
        hub_variant = "large"

    # Load listing (enforce tenant/partner and optionally agent)
    where = [
        Listing.id == listing_id,
        Listing.tenant_id == tenant_id,
        Listing.partner_id == partner_id,
    ]
    if agent_id:
        where.append(Listing.agent_id == agent_id)

    listing = (await db.execute(select(Listing).where(*where))).scalar_one_or_none()
    if not listing:
        raise ValueError("Listing not found")

    # Build canonical payload but prefer Hub media URLs if listing_media exists.
    canonical_payload = dict(listing.payload or {})

    if use_hub_media:
        media_items = await resolve_listing_media_urls(
            db,
            tenant_id=tenant_id,
            partner_id=partner_id,
            agent_id=agent_id,
            expected_agent_id=listing.agent_id,          
            listing_id=listing.id,
            variant=hub_variant,
        )

        if media_items:
            canonical_payload["media"] = [
                {
                    "url": mi["url"],
                    "type": mi["type"],
                    "order": mi["order"],
                    "caption": mi["caption"],
                }
                for mi in media_items
            ]

    Model = resolve_schema(listing.schema, listing.schema_version)
    canonical_any = Model.model_validate(canonical_payload)

    if not isinstance(canonical_any, ListingCanonicalV1):
        raise ValueError(
            f"Unsupported canonical type for publish: {listing.schema}@{listing.schema_version}"
        )

    canonical = canonical_any

    mapping = (await db.execute(
        select(ListingExternalMapping).where(
            ListingExternalMapping.tenant_id == tenant_id,
            ListingExternalMapping.destination == dest,
            ListingExternalMapping.listing_id == listing.id,
        )
    )).scalar_one_or_none()

    ext_agent = None
    if agent_id is not None:
        ext_agent = (await db.execute(
            select(AgentExternalIdentity).where(
                AgentExternalIdentity.tenant_id == tenant_id,
                AgentExternalIdentity.partner_id == partner_id,
                AgentExternalIdentity.agent_id == agent_id,
                AgentExternalIdentity.destination == dest,
                AgentExternalIdentity.is_active.is_(True),
            )
        )).scalar_one_or_none()

    projector = get_projector(dest)

    projected = projector.project_listing(
        canonical=canonical,
        ctx=ProjectionContext(
            tenant_id=tenant_id,
            partner_id=partner_id,
            agent_id=agent_id,
            destination=dest,
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
    agent_id: str | None,
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
    mode: str = "live",
    request_id: str | None = None,
):
    connector = get_destination_connector(destination)
    return await connector.publish_listing(
        payload=payload,
        credentials=credentials,
        mode=mode,
        request_id=request_id,
    )

async def publish_projected_payload_for_delivery(
    db: AsyncSession,
    *,
    tenant_id: str,
    partner_id: str,
    destination: str,
    payload: dict,
    credentials: dict,
    request_id: str | None = None,
):
    setting = (await db.execute(
        select(PartnerDestinationSetting).where(
            PartnerDestinationSetting.tenant_id == tenant_id,
            PartnerDestinationSetting.partner_id == partner_id,
            PartnerDestinationSetting.destination == destination.lower().strip(),
            PartnerDestinationSetting.is_enabled.is_(True),
        )
    )).scalar_one_or_none()

    mode = destination_mode(setting.config if setting else None)

    return await publish_projected_payload(
        destination=destination,
        payload=payload,
        credentials=credentials,
        mode=mode,
        request_id=request_id,
    )