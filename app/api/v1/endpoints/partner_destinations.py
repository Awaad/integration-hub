from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.partner_destination_setting import PartnerDestinationSetting
from app.schemas.partner_destination import PartnerDestinationUpsert, PartnerDestinationOut
from app.services.auth import Actor, require_partner_admin
from app.destinations.connector_registry import supported_destinations

router = APIRouter()

@router.get("/partners/{partner_id}/destinations", response_model=list[PartnerDestinationOut])
async def list_partner_destinations(
    partner_id: str,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
):
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    rows = (await db.execute(select(PartnerDestinationSetting).where(
        PartnerDestinationSetting.tenant_id == actor.tenant_id,
        PartnerDestinationSetting.partner_id == partner_id,
    ).order_by(PartnerDestinationSetting.destination.asc()))).scalars().all()

    return [
        PartnerDestinationOut(
            destination=r.destination,
            is_enabled=r.is_enabled,
            config=r.config,
            created_by=r.created_by,
            updated_by=r.updated_by,
        )
        for r in rows
    ]


@router.put("/partners/{partner_id}/destinations/{destination}", response_model=PartnerDestinationOut)
async def upsert_partner_destination(
    partner_id: str,
    destination: str,
    body: PartnerDestinationUpsert,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
):
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    dest_norm = destination.lower().strip()

    # enforce destination exists in registry
    if dest_norm not in supported_destinations():
        raise HTTPException(status_code=404, detail=f"Unknown destination: {dest_norm}")

    stmt = (
        insert(PartnerDestinationSetting)
        .values(
            tenant_id=actor.tenant_id,
            partner_id=partner_id,
            destination=dest_norm,
            is_enabled=body.is_enabled,
            config=body.config,
            created_by=actor.api_key_id,
            updated_by=actor.api_key_id,
        )
        .on_conflict_do_update(
            constraint="uq_partner_destination",
            set_={
                "is_enabled": body.is_enabled,
                "config": body.config,
                "updated_by": actor.api_key_id,
            },
        )
        .returning(PartnerDestinationSetting)
    )

    row = (await db.execute(stmt)).scalar_one()
    await db.commit()

    return PartnerDestinationOut(
        destination=row.destination,
        is_enabled=row.is_enabled,
        config=row.config,
        created_by=row.created_by,
        updated_by=row.updated_by,
    )
