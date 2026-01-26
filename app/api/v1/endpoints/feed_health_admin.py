from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.feed_snapshot import FeedSnapshot
from app.services.internal_admin import require_internal_admin

router = APIRouter()


@router.get("/admin/health/feeds", dependencies=[Depends(require_internal_admin)])
async def feeds_health_admin(
    stale_minutes: int = Query(default=30, ge=1, le=1440),
    limit: int = Query(default=500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
):
    # Simple approach: grab recent snapshots then dedupe.
    # TODO (perf): switch to DISTINCT ON (tenant_id, partner_id, destination) in Postgres.
    rows = (
        await db.execute(
            select(FeedSnapshot)
            .order_by(desc(FeedSnapshot.created_at))
            .limit(limit)
        )
    ).scalars().all()

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=stale_minutes)

    # Deduplicate by (tenant_id, partner_id, destination) picking newest
    latest_by: dict[tuple[str | None, str, str], FeedSnapshot] = {}
    for s in rows:
        k = (getattr(s, "tenant_id", None), s.partner_id, s.destination)
        if k not in latest_by:
            latest_by[k] = s

    latest = list(latest_by.values())

    stale = []
    for s in latest:
        if s.created_at and s.created_at < cutoff:
            meta = s.meta or {}
            stale.append({
                "tenant_id": getattr(s, "tenant_id", None),
                "partner_id": s.partner_id,
                "destination": s.destination,
                "age_minutes": int((now - s.created_at).total_seconds() // 60),
                "created_at": s.created_at.isoformat(),
                "listing_count": s.listing_count,
                "warnings_count": meta.get("warnings_count", 0),
                "skipped_count": meta.get("skipped_count", 0),
                "parse_ok": meta.get("parse_ok", True),
                "parse_ms": meta.get("parse_ms", 0),
                "listing_inclusion_policy": meta.get("listing_inclusion_policy"),
                "generator": meta.get("generator"),
            })

    # Top warning feeds (include parse_ok and skipped_count)
    top_warning_feeds = sorted(
        [
            {
                "tenant_id": getattr(s, "tenant_id", None),
                "partner_id": s.partner_id,
                "destination": s.destination,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "listing_count": s.listing_count,
                "warnings_count": (s.meta or {}).get("warnings_count", 0),
                "skipped_count": (s.meta or {}).get("skipped_count", 0),
                "parse_ok": (s.meta or {}).get("parse_ok", True),
                "parse_ms": (s.meta or {}).get("parse_ms", 0),
                "listing_inclusion_policy": (s.meta or {}).get("listing_inclusion_policy"),
                "generator": (s.meta or {}).get("generator"),
            }
            for s in latest
        ],
        key=lambda x: (x["warnings_count"], x["skipped_count"]),
        reverse=True,
    )[:20]

    # count parse failures
    parse_failures = [
        {
            "tenant_id": getattr(s, "tenant_id", None),
            "partner_id": s.partner_id,
            "destination": s.destination,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "warnings_count": (s.meta or {}).get("warnings_count", 0),
            "skipped_count": (s.meta or {}).get("skipped_count", 0),
            "parse_ms": (s.meta or {}).get("parse_ms", 0),
        }
        for s in latest
        if (s.meta or {}).get("parse_ok") is False
    ][:50]

    return {
        "stale_cutoff_minutes": stale_minutes,
        "latest_count": len(latest),
        "stale": stale,
        "top_warning_feeds": top_warning_feeds,
        "parse_failures": parse_failures,
        "note": "This endpoint dedupes from the most recent snapshots. Increase limit if you have many partners; later switch to DISTINCT ON for correctness+speed.",
    }
