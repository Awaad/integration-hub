from __future__ import annotations
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import FileResponse

from app.core.db import get_db
from app.models.partner_destination_setting import PartnerDestinationSetting
from app.models.feed_snapshot import FeedSnapshot

router = APIRouter()

@router.get("/feeds/{partner_id}/{destination}.xml")
async def get_public_feed_xml(
    partner_id: str,
    destination: str,
    token: str = Query(..., min_length=10),
    db: AsyncSession = Depends(get_db),
):
    dest = destination.lower().strip()

    setting = (await db.execute(
        select(PartnerDestinationSetting).where(
            PartnerDestinationSetting.partner_id == partner_id,
            PartnerDestinationSetting.destination == dest,
            PartnerDestinationSetting.is_enabled.is_(True),
        )
    )).scalar_one_or_none()

    if not setting:
        raise HTTPException(status_code=404, detail="Feed not enabled")

    cfg = setting.config or {}
    if cfg.get("feed_token") != token:
        raise HTTPException(status_code=403, detail="Invalid token")

    snap = (await db.execute(
        select(FeedSnapshot).where(
            FeedSnapshot.partner_id == partner_id,
            FeedSnapshot.destination == dest,
        ).order_by(desc(FeedSnapshot.created_at)).limit(1)
    )).scalar_one_or_none()

    if not snap:
        raise HTTPException(status_code=404, detail="No snapshot available")

    # storage_uri is currently file://...
    parsed = urlparse(snap.storage_uri)
    if parsed.scheme != "file":
        raise HTTPException(status_code=501, detail="Non-file storage not supported yet")

    path = Path(parsed.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Snapshot file missing")

    return FileResponse(path, media_type="application/xml")
