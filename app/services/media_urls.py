from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.listing_media import ListingMedia
from app.models.media_object import MediaObject
from app.models.partner_public_token import PartnerPublicToken

_ALLOWED_VARIANTS = {"orig", "thumb", "medium", "large"}


async def resolve_listing_media_urls(
    db: AsyncSession,
    *,
    tenant_id: str,
    partner_id: str,
    agent_id: str | None,
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
    ]
    if agent_id is not None:
        where_clauses.append(ListingMedia.agent_id == agent_id)

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

    # Only emit Hub URLs if partner has an active media token.
    tok_exists = (
        await db.execute(
            select(PartnerPublicToken.id).where(
                PartnerPublicToken.tenant_id == tenant_id,
                PartnerPublicToken.partner_id == partner_id,
                PartnerPublicToken.scope == "media",
                PartnerPublicToken.is_active.is_(True),
            ).limit(1)
        )
    ).scalar_one_or_none()

    if not tok_exists:
        # no token -> fallback to canonical/raw
        return []

    base = settings.public_base_url.rstrip("/")
    out: list[dict[str, Any]] = []

    for lm, m in rows:
        qs = urlencode({"variant": variant})
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
