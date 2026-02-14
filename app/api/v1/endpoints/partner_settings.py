from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.partner_settings import PartnerSettings
from app.schemas.partner_settings import PartnerSettingsPayload
from app.services.partner_settings_service import (
    get_partner_settings,
    merge_with_defaults,
)

from app.services.auth import require_partner_admin, Actor

router = APIRouter(prefix="/partners/{partner_id}/settings")


@router.get("", response_model=PartnerSettingsPayload)
async def read_settings(
    partner_id: str,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
):
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Access denied for this partner")

    return await get_partner_settings(
        db,
        tenant_id=actor.tenant_id,
        partner_id=partner_id,
    )


@router.put("", response_model=PartnerSettingsPayload)
async def update_settings(
    partner_id: str,
    payload: PartnerSettingsPayload,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
):
    if actor.partner_id and actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Access denied for this partner")

    pk = f"{actor.tenant_id}:{partner_id}"

    row = await db.get(PartnerSettings, pk)

    validated_config = merge_with_defaults(payload.model_dump())

    if not row:
        row = PartnerSettings(
            id=pk,
            tenant_id=actor.tenant_id,
            partner_id=partner_id,
            config=validated_config,
            created_by=actor.api_key_id,
            updated_by=actor.api_key_id,
        )
        db.add(row)
    else:
        row.config = validated_config
        row.updated_by = actor.api_key_id

    await db.commit()
    await db.refresh(row)

    return merge_with_defaults(row.config)