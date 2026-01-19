from __future__ import annotations
import gzip
from datetime import timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, Depends, Request
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import FileResponse, Response

from app.core.db import get_db
from app.models.partner_destination_setting import PartnerDestinationSetting
from app.models.feed_snapshot import FeedSnapshot

router = APIRouter()

# Dispatcher polls every 30s; 60s cache is a reasonable default.
CACHE_MAX_AGE_SECONDS = 60


def _http_date(dt) -> str:
    if dt is None:
        return ""
    if getattr(dt, "tzinfo", None) is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt.astimezone(timezone.utc), usegmt=True)


def _etag_value(content_hash: str) -> str:
    # Strong ETag, quoted per RFC.
    return f"\"{content_hash}\""


def _if_none_match_matches(if_none_match: str | None, etag: str) -> bool:
    if not if_none_match:
        return False
    # Can be: *, "abc", W/"abc", or multiple comma-separated values
    parts = [p.strip() for p in if_none_match.split(",")]
    for p in parts:
        if p == "*":
            return True
        # Strip weak validator prefix
        if p.startswith("W/"):
            p = p[2:].strip()
        if p == etag:
            return True
    return False


@router.get("/feeds/{partner_id}/{destination}.xml")
async def get_public_feed_xml(
    partner_id: str,
    destination: str,
    request: Request,
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


    etag = _etag_value(snap.content_hash)
    last_modified = _http_date(snap.created_at)

    common_headers = {
        "ETag": etag,
        "Cache-Control": f"public, max-age={CACHE_MAX_AGE_SECONDS}",
        "Last-Modified": last_modified,
        "Vary": "Accept-Encoding",
    }

    # Conditional request
    if _if_none_match_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=common_headers)

    accept_encoding = (request.headers.get("accept-encoding") or "").lower()
    wants_gzip = "gzip" in accept_encoding

    chosen_uri = snap.storage_uri
    content_encoding = None

    if wants_gzip and snap.gzip_storage_uri:
        chosen_uri = snap.gzip_storage_uri
        content_encoding = "gzip"
    

    # storage_uri is currently file://...
    parsed = urlparse(chosen_uri)
    if parsed.scheme != "file":
        raise HTTPException(status_code=501, detail="Non-file storage not supported yet")

    path = Path(parsed.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Snapshot file missing")
    
    headers = dict(common_headers)
    if content_encoding:
        headers["Content-Encoding"] = content_encoding

    # Normal (uncompressed)
    return FileResponse(path, media_type="application/xml", headers=headers)
