from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.feed_snapshot import FeedSnapshot
from app.services.auth import Actor, require_partner_admin

router = APIRouter()

@router.get("/partners/{partner_id}/destinations/{destination}/feed/latest")
async def get_latest_feed(
    partner_id: str,
    destination: str,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
):
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    dest = destination.lower().strip()

    snap = (await db.execute(
        select(FeedSnapshot).where(
            FeedSnapshot.tenant_id == actor.tenant_id,
            FeedSnapshot.partner_id == partner_id,
            FeedSnapshot.destination == dest,
        ).order_by(desc(FeedSnapshot.created_at)).limit(1)
    )).scalar_one_or_none()

    if not snap:
        raise HTTPException(status_code=404, detail="No feed snapshot found")

    return {
        "destination": dest,
        "storage_uri": snap.storage_uri,
        "format": snap.format,
        "content_hash": snap.content_hash,
        "listing_count": snap.listing_count,
        "created_at": str(snap.created_at),
    }
