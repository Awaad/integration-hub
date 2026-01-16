from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.ingest_run import IngestRun
from app.services.auth import Actor, require_partner_admin

router = APIRouter()

@router.get("/partners/{partner_id}/ingest-runs", response_model=list[dict])
async def list_ingest_runs(
    partner_id: str,
    source_listing_id: str | None = Query(default=None),
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
):
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    stmt = select(IngestRun).where(
        IngestRun.tenant_id == actor.tenant_id,
        IngestRun.partner_id == partner_id,
    ).order_by(IngestRun.created_at.desc()).limit(50)

    if source_listing_id:
        stmt = stmt.where(IngestRun.source_listing_id == source_listing_id)

    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "partner_key": r.partner_key,
            "source_listing_id": r.source_listing_id,
            "idempotency_key": r.idempotency_key,
            "status": r.status,
            "listing_id": r.listing_id,
            "errors": r.errors,
            "created_at": str(r.created_at),
        }
        for r in rows
    ]
