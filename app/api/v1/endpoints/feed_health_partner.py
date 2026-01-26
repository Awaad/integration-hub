from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.feed_snapshot import FeedSnapshot
from app.services.auth import Actor, require_partner_admin

router = APIRouter()


@router.get("/partners/{partner_id}/destinations/{destination}/feed-health")
async def feed_health_partner(
    partner_id: str,
    destination: str,
    stale_minutes: int = Query(default=30, ge=1, le=1440),
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
):
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    dest = destination.lower().strip()

    snap = (
        await db.execute(
            select(FeedSnapshot).where(
                FeedSnapshot.tenant_id == actor.tenant_id,
                FeedSnapshot.partner_id == partner_id,
                FeedSnapshot.destination == dest,
            ).order_by(desc(FeedSnapshot.created_at)).limit(1)
        )
    ).scalar_one_or_none()

    if not snap:
        raise HTTPException(status_code=404, detail="No snapshot available")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=stale_minutes)
    is_stale = bool(snap.created_at and snap.created_at < cutoff)

    meta = snap.meta or {}

    return {
        "partner_id": partner_id,
        "destination": dest,
        "stale": is_stale,
        "stale_cutoff_minutes": stale_minutes,
        "latest_snapshot": {
            "created_at": snap.created_at.isoformat() if snap.created_at else None,
            "content_hash": snap.content_hash,
            "format": snap.format,
            "listing_count": snap.listing_count,
            "generator": meta.get("generator"),
            "listing_inclusion_policy": meta.get("listing_inclusion_policy"),
            "warnings_count": meta.get("warnings_count", 0),
            "warnings_by_code": meta.get("warnings_by_code", {}),
            "skipped_count": meta.get("skipped_count", 0),
            "skipped_by_reason": meta.get("skipped_by_reason", {}),
            "parse_ok": meta.get("parse_ok", True),
            "parse_ms": meta.get("parse_ms", 0),
        },
    }
