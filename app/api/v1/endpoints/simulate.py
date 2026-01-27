from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.services.auth import Actor, require_partner_admin
from app.models.partner_destination_setting import PartnerDestinationSetting
from app.services.destination_config import destination_mode
from app.services.simulate_service import build_projected_payload_for_listing
from app.services.audit import audit


router = APIRouter()

@router.post("/partners/{partner_id}/destinations/{destination}/simulate")
async def simulate_destination_publish(
    partner_id: str,
    destination: str,
    body: dict,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
):
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    dest = destination.lower().strip()
    listing_id = body.get("listing_id")
    if not listing_id:
        raise HTTPException(status_code=422, detail="listing_id required")

    setting = (await db.execute(select(PartnerDestinationSetting).where(
        PartnerDestinationSetting.tenant_id == actor.tenant_id,
        PartnerDestinationSetting.partner_id == partner_id,
        PartnerDestinationSetting.destination == dest,
        PartnerDestinationSetting.is_enabled.is_(True),
    ))).scalar_one_or_none()
    if not setting:
        raise HTTPException(status_code=404, detail="Destination not enabled")

    mode = destination_mode(setting.config)

    try:
        projected, external_listing_id, listing_agent_id = await build_projected_payload_for_listing(
            db,
            tenant_id=actor.tenant_id,
            partner_id=partner_id,
            destination=dest,
            listing_id=listing_id,
        )
    except ValueError as e:
        if str(e) == "listing_not_found":
            raise HTTPException(status_code=404, detail="Listing not found")
        raise

    # Enforce: agent keys can only simulate their own listing
    if actor.agent_id and actor.agent_id != listing_agent_id:
        raise HTTPException(status_code=403, detail="Agent cannot simulate another agent's listing")

    await audit(
        db,
        tenant_id=actor.tenant_id,
        partner_id=partner_id,
        actor_api_key_id=actor.api_key_id,
        action="destination.simulate",
        target_type="listing",
        target_id=listing_id,
        detail={"destination": dest, "mode": mode, "external_listing_id": external_listing_id},
    )
    await db.commit()

    return {
        "destination": dest,
        "mode": mode,
        "listing_id": listing_id,
        "external_listing_id": external_listing_id,
        "projected_payload": projected,
        "note": "Simulation only. No external call performed.",
    }