from app.services.audit import audit
from app.services.feed_urls import build_public_feed_url
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import secrets
from app.core.config import settings
from app.core.db import get_db
from app.models.partner_destination_setting import PartnerDestinationSetting
from app.services.auth import Actor, require_partner_admin
from app.services.partner_destination_config import ensure_feed_token



router = APIRouter()

@router.get("/partners/{partner_id}/destinations/{destination}/feed-url")
async def get_feed_url(
    partner_id: str,
    destination: str,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
):
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    dest = destination.lower().strip()

    setting = (await db.execute(select(PartnerDestinationSetting).where(
        PartnerDestinationSetting.tenant_id == actor.tenant_id,
        PartnerDestinationSetting.partner_id == partner_id,
        PartnerDestinationSetting.destination == dest,
        PartnerDestinationSetting.is_enabled.is_(True),
    ))).scalar_one_or_none()
    if not setting:
        raise HTTPException(status_code=404, detail="Destination not enabled")

    token = await ensure_feed_token(db, tenant_id=actor.tenant_id, partner_id=partner_id, destination=dest)
    await db.commit()


    return {
        "destination": dest,
        "feed_url": build_public_feed_url(
            public_base_url=settings.public_base_url,
            partner_id=partner_id,
            destination=dest,
            token=token,
        ),
    }

@router.post("/partners/{partner_id}/destinations/{destination}/feed-token:rotate")
async def rotate_feed_token(
    partner_id: str,
    destination: str,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
):
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    dest = destination.lower().strip()
    setting = (await db.execute(select(PartnerDestinationSetting).where(
        PartnerDestinationSetting.tenant_id == actor.tenant_id,
        PartnerDestinationSetting.partner_id == partner_id,
        PartnerDestinationSetting.destination == dest,
        PartnerDestinationSetting.is_enabled.is_(True),
    ))).scalar_one_or_none()
    if not setting:
        raise HTTPException(status_code=404, detail="Destination not enabled")

    cfg = dict(setting.config or {})
    cfg["feed_token"] = secrets.token_urlsafe(24)
    setting.config = cfg
    setting.updated_by = actor.api_key_id

    await audit(
        db,
        tenant_id=actor.tenant_id,
        partner_id=partner_id,
        actor_api_key_id=actor.api_key_id,
        action="feed_token.rotated",
        target_type="partner_destination_setting",
        target_id=f"{partner_id}:{dest}",
        detail={"destination": dest},
    )
    
    await db.commit()

    return {
        "destination": dest,
        "feed_url": build_public_feed_url(
            public_base_url=settings.public_base_url,
            partner_id=partner_id,
            destination=dest,
            token=cfg["feed_token"],
        ),
    }
