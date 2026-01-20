from __future__ import annotations
import hashlib
from datetime import timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlparse

from app.destinations.feeds.registry import get_feed_plugin
from app.services.rate_limit import TokenRateLimiter
from app.services.storage import LocalObjectStore
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import FileResponse, Response

from app.core.config import settings
from app.core.db import get_db
from app.models.partner_destination_setting import PartnerDestinationSetting
from app.models.feed_snapshot import FeedSnapshot

router = APIRouter()

# Dispatcher polls every 30s; 60s cache is a reasonable default.
CACHE_MAX_AGE_SECONDS = 60

# Create once (reuse Redis pool)
_limiter = TokenRateLimiter(settings.redis_url)
_store = LocalObjectStore(settings.feed_storage_dir)

def _media_type(ext: str) -> str:
    ext = (ext or "").lower().strip()
    if ext == "xml":
        return "application/xml"
    if ext == "csv":
        return "text/csv; charset=utf-8"
    if ext == "json":
        return "application/json"
    return "application/octet-stream"

def _http_date(dt) -> str:
    if dt is None:
        return ""
    if getattr(dt, "tzinfo", None) is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt.astimezone(timezone.utc), usegmt=True)


def _etag_value(content_hash: str) -> str:
    # Strong ETag
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

def _token_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


async def _rate_limit_or_429(*, partner_id: str, dest: str, token: str) -> dict[str, str]:
    rl = await _limiter.allow(
        key=f"public_feed:{partner_id}:{dest}:{_token_key(token)}",
        limit=60,
        window_seconds=60,
    )
    if not rl.allowed:
        # include Retry-After
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(rl.reset_seconds)},
        )

    return {
        "X-RateLimit-Limit": "60",
        "X-RateLimit-Remaining": str(rl.remaining),
        "X-RateLimit-Reset": str(rl.reset_seconds),
    }


async def _resolve_snapshot_and_headers(
    *,
    db: AsyncSession,
    store: LocalObjectStore,
    partner_id: str,
    destination: str,
    ext: str,
    token: str,
    request: Request,
):
    dest = destination.lower().strip()
    ext = ext.lower().strip()

    # Validate ext matches plugin contract
    try:
        plugin = get_feed_plugin(dest)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown destination: {dest}")

    if ext != plugin.format:
        raise HTTPException(status_code=404, detail="Unsupported format")

    setting = (
        await db.execute(
            select(PartnerDestinationSetting).where(
                PartnerDestinationSetting.partner_id == partner_id,
                PartnerDestinationSetting.destination == dest,
                PartnerDestinationSetting.is_enabled.is_(True),
            )
        )
    ).scalar_one_or_none()

    if not setting:
        raise HTTPException(status_code=404, detail="Feed not enabled")

    cfg = setting.config or {}
    if cfg.get("feed_token") != token:
        raise HTTPException(status_code=403, detail="Invalid token")

    snap = (
        await db.execute(
            select(FeedSnapshot).where(
                FeedSnapshot.partner_id == partner_id,
                FeedSnapshot.destination == dest,
            ).order_by(desc(FeedSnapshot.created_at)).limit(1)
        )
    ).scalar_one_or_none()

    if not snap:
        raise HTTPException(status_code=404, detail="No snapshot available")

     # extra safety: snapshot format should match ext
    if (snap.format or "").lower().strip() != ext:
        raise HTTPException(status_code=404, detail="No snapshot available for requested format")
    
    etag = _etag_value(snap.content_hash)
    last_modified = _http_date(snap.created_at)

    headers = {
        "ETag": etag,
        "Cache-Control": f"public, max-age={CACHE_MAX_AGE_SECONDS}",
        "Last-Modified": last_modified,
        "Vary": "Accept-Encoding",
    }

    accept_encoding = (request.headers.get("accept-encoding") or "").lower()
    wants_gzip = "gzip" in accept_encoding

    chosen_uri = snap.storage_uri
    if wants_gzip and snap.gzip_storage_uri:
        chosen_uri = snap.gzip_storage_uri
        headers["Content-Encoding"] = "gzip"

    try:
        path = store.resolve_path(chosen_uri)
    except ValueError:
        raise HTTPException(status_code=501, detail="Non-file storage not supported yet")

    if not path.exists():
        raise HTTPException(status_code=404, detail="Snapshot file missing")

    return dest, path, headers


@router.get("/feeds/{partner_id}/{destination}.xml")
async def get_public_feed_xml(
    partner_id: str,
    destination: str,
    ext: str,
    request: Request,
    token: str = Query(..., min_length=10),
    db: AsyncSession = Depends(get_db),
):

    dest, path, headers = await _resolve_snapshot_and_headers(
        db=db,
        store=_store,
        partner_id=partner_id,
        destination=destination,
        ext=ext,
        token=token,
        request=request,
    )

    # Rate limit (after auth)
    rl_headers = await _rate_limit_or_429(partner_id=partner_id, dest=dest, token=token)
    headers.update(rl_headers)

    if _if_none_match_matches(request.headers.get("if-none-match"), headers["ETag"]):
        return Response(status_code=304, headers=headers)

    return FileResponse(path, media_type=_media_type(ext), headers=headers)


@router.head("/feeds/{partner_id}/{destination}.{ext}")
async def head_public_feed_xml(
    partner_id: str,
    destination: str,
    ext: str,
    request: Request,
    token: str = Query(..., min_length=10),
    db: AsyncSession = Depends(get_db),
):

    dest, path, headers = await _resolve_snapshot_and_headers(
        db=db,
        store=_store,
        partner_id=partner_id,
        destination=destination,
        ext=ext,
        token=token,
        request=request,
    )

    rl_headers = await _rate_limit_or_429(partner_id=partner_id, dest=dest, token=token)
    headers.update(rl_headers)

    if _if_none_match_matches(request.headers.get("if-none-match"), headers["ETag"]):
        return Response(status_code=304, headers=headers)

    return Response(status_code=200, headers=headers)