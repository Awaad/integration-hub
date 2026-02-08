from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.listing_media import ListingMedia
from app.models.media_object import MediaObject
from app.models.partner_public_token import PartnerPublicToken

_ALLOWED_VARIANTS = {"orig", "thumb", "medium", "large"}
_DEFAULT_CHUNK = 1000

async def partner_has_active_media_token(
    db: AsyncSession,
    *,
    tenant_id: str,
    partner_id: str,
) -> bool:
    tok_exists = (
        await db.execute(
            select(PartnerPublicToken.id)
            .where(
                PartnerPublicToken.tenant_id == tenant_id,
                PartnerPublicToken.partner_id == partner_id,
                PartnerPublicToken.scope == "media",
                PartnerPublicToken.is_active.is_(True),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return bool(tok_exists)


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


async def resolve_listing_media_urls_bulk(
    db: AsyncSession,
    *,
    tenant_id: str,
    partner_id: str,
    listing_ids: Iterable[str],
    agent_id: str | None = None,
    expected_agent_id: str | None = None,
    variant: str = "large",
    chunk_size: int = _DEFAULT_CHUNK,
) -> dict[str, list[dict[str, Any]]]:
    listing_ids = sorted({lid for lid in listing_ids if lid})
    if not listing_ids:
        return {}

    variant = (variant or "large").lower().strip()
    if variant not in _ALLOWED_VARIANTS:
        variant = "large"

    chunk_size = int(chunk_size or _DEFAULT_CHUNK)
    chunk_size = max(50, min(chunk_size, 5000))

    if not await partner_has_active_media_token(db, tenant_id=tenant_id, partner_id=partner_id):
        return {}

    base = settings.public_base_url.rstrip("/")
    qs = urlencode({"variant": variant})

    out: dict[str, list[dict[str, Any]]] = {}

    for batch in _chunks(listing_ids, int(chunk_size) or _DEFAULT_CHUNK):
        where_clauses = [
            ListingMedia.tenant_id == tenant_id,
            ListingMedia.partner_id == partner_id,
            ListingMedia.listing_id.in_(batch),
            MediaObject.tenant_id == tenant_id,
            MediaObject.partner_id == partner_id,
            ListingMedia.agent_id == MediaObject.agent_id,
        ]
        if agent_id is not None:
            where_clauses.append(ListingMedia.agent_id == agent_id)
            
        if expected_agent_id is not None:
            where_clauses.append(ListingMedia.agent_id == expected_agent_id)

        rows = (
            await db.execute(
                select(ListingMedia, MediaObject)
                .join(MediaObject, MediaObject.id == ListingMedia.media_id)
                .where(*where_clauses)
                .order_by(
                    ListingMedia.listing_id.asc(),
                    ListingMedia.is_primary.desc(),
                    ListingMedia.order_index.asc(),
                    ListingMedia.created_at.asc(),
                )
            )
        ).all()

        for lm, m in rows:
            url = f"{base}/public/media/{m.id}/r?{qs}"
            out.setdefault(lm.listing_id, []).append(
                {
                    "url": url,
                    "type": lm.type,
                    "order": lm.order_index,
                    "caption": lm.caption,
                    "media_id": m.id,
                    "is_primary": lm.is_primary,
                }
            )

    return out


async def resolve_listing_media_urls(
    db: AsyncSession,
    *,
    tenant_id: str,
    partner_id: str,
    agent_id: str | None,
    expected_agent_id: str | None = None,
    listing_id: str,
    variant: str = "large",
) -> list[dict[str, Any]]:
    """
    If listing_media exists => return Hub signed public URLs.
    If not => return [] (caller can fallback to canonical/raw URLs).
    """

    variant = (variant or "large").lower().strip()
    if variant not in _ALLOWED_VARIANTS:
        variant = "large"

    where_clauses = [
        ListingMedia.tenant_id == tenant_id,
        ListingMedia.partner_id == partner_id,
        ListingMedia.listing_id == listing_id,
        MediaObject.tenant_id == tenant_id,
        MediaObject.partner_id == partner_id,
        ListingMedia.agent_id == MediaObject.agent_id
    ]
    if agent_id is not None:
        where_clauses.append(ListingMedia.agent_id == agent_id)

    if expected_agent_id is not None:
        where_clauses.append(ListingMedia.agent_id == expected_agent_id)

    rows = (
        await db.execute(
            select(ListingMedia, MediaObject)
            .join(MediaObject, MediaObject.id == ListingMedia.media_id)
            .where(*where_clauses)
            .order_by(
                ListingMedia.is_primary.desc(),
                ListingMedia.order_index.asc(),
                ListingMedia.created_at.asc(),
            )
        )
    ).all()

    if not rows:
        return []

    if not await partner_has_active_media_token(db, tenant_id=tenant_id, partner_id=partner_id):
        return []

    base = settings.public_base_url.rstrip("/")
    out: list[dict[str, Any]] = []

    qs = urlencode({"variant": variant})
    for lm, m in rows:
        url = f"{base}/public/media/{m.id}/r?{qs}"

        out.append(
            {
                "url": url,
                "type": lm.type,
                "order": lm.order_index,
                "caption": lm.caption,
                "media_id": m.id,
                "is_primary": lm.is_primary,
            }
        )

    return out
