from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.delivery import Delivery, DeliveryAttempt
from app.schemas.delivery import DeliveryOut, DeliveryAttemptOut
from app.services.auth import Actor, require_partner_admin

router = APIRouter()

@router.get("/partners/{partner_id}/deliveries", response_model=list[DeliveryOut])
async def list_deliveries(
    partner_id: str,
    status: str | None = Query(default=None),
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
) -> list[DeliveryOut]:
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    stmt = select(Delivery).where(Delivery.partner_id == partner_id, Delivery.tenant_id == actor.tenant_id)
    if status:
        stmt = stmt.where(Delivery.status == status)

    rows = (await db.execute(stmt)).scalars().all()
    return [
        DeliveryOut(
            id=r.id,
            listing_id=r.listing_id,
            agent_id=r.agent_id,
            destination=r.destination,
            status=r.status,
            attempts=r.attempts,
            last_error=r.last_error,
            status_detail=r.status_detail,
            dead_lettered_at=str(r.dead_lettered_at) if r.dead_lettered_at else None,
        )
        for r in rows
    ]

@router.get("/partners/{partner_id}/deliveries/{delivery_id}/attempts", response_model=list[DeliveryAttemptOut])
async def list_delivery_attempts(
    partner_id: str,
    delivery_id: str,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
) -> list[DeliveryAttemptOut]:
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    d = (await db.execute(select(Delivery).where(
        Delivery.id == delivery_id,
        Delivery.partner_id == partner_id,
        Delivery.tenant_id == actor.tenant_id,
    ))).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Delivery not found")

    rows = (await db.execute(select(DeliveryAttempt).where(DeliveryAttempt.delivery_id == delivery_id))).scalars().all()
    return [
        DeliveryAttemptOut(
            id=a.id,
            delivery_id=a.delivery_id,
            status=a.status,
            error_code=a.error_code,
            error_message=a.error_message,
            request=a.request,
            response=a.response,
            created_at=str(a.created_at),
        )
        for a in rows
    ]
