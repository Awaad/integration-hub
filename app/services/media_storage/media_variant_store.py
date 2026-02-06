from __future__ import annotations

import hashlib
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.media_object import MediaObject
from app.models.media_variant import MediaVariant
from app.services.media_storage.provider import get_media_storage
from app.services.media_variant_keys import build_variant_storage_key
from app.services.media_variants import generate_variant_from_path


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def get_or_create_variant(
    db: AsyncSession,
    *,
    media: MediaObject,
    variant: str,
) -> MediaVariant:
    variant = variant.strip().lower()

    # quick read
    row = (
        await db.execute(
            select(MediaVariant).where(
                MediaVariant.media_id == media.id,
                MediaVariant.variant == variant,
            )
        )
    ).scalar_one_or_none()
    if row:
        return row

    if media.storage_backend != "local":
        raise ValueError("unsupported backend")

    max_dim = settings.media_variants.get(variant)
    if not max_dim:
        raise ValueError("unknown variant")
    max_dim = int(max_dim)

    out_format = str(getattr(settings, "media_variant_format", "webp")).lower()
    quality = int(getattr(settings, "media_variant_quality", 82))
    version = str(getattr(settings, "media_variant_pipeline_version", "v1"))

    ext = "webp" if out_format == "webp" else "jpg"

    storage = get_media_storage()

    # Load original bytes via safe local path
    src_path = storage.resolve_local_path(backend=media.storage_backend, key=media.storage_key)
    if not src_path or not src_path.exists():
        raise ValueError("source media missing")

    out_bytes, w, h, mime = generate_variant_from_path(
        src_path=src_path,
        max_dim=max_dim,
        out_format=out_format.upper(),
        quality=quality,
    )

    variant_hash = _sha256_hex(out_bytes)

    variant_key = build_variant_storage_key(
        tenant_id=media.tenant_id,
        partner_id=media.partner_id,
        agent_id=media.agent_id,
        media_id=media.id,
        version=version,
        variant=variant,
        ext=ext,
    )

    stored = await storage.put_bytes_at_key(key=variant_key, data=out_bytes)

    mv = MediaVariant(
        tenant_id=media.tenant_id,
        partner_id=media.partner_id,
        agent_id=media.agent_id,
        media_id=media.id,
        variant=variant,
        variant_hash=variant_hash,
        mime_type=mime,
        byte_size=stored.byte_size,
        storage_backend=stored.backend,
        storage_key=stored.key,
        width=w,
        height=h,
    )

    try:
        async with db.begin_nested():
            db.add(mv)
            await db.flush()
        return mv
    except IntegrityError:
        # someone else won; fetch and return
        winner = (
            await db.execute(
                select(MediaVariant).where(
                    MediaVariant.media_id == media.id,
                    MediaVariant.variant == variant,
                )
            )
        ).scalar_one()
        return winner
