from __future__ import annotations
import hashlib
import os
import tempfile
from pathlib import Path
import anyio

from sqlalchemy.exc import IntegrityError
import httpx
from app.services.http_client import HubHttpClient

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.media_object import MediaObject
from app.services.media_storage.provider import get_media_storage
from app.core.ids import gen_id

MAX_MEDIA_BYTES = 25 * 1024 * 1024  # 25MB

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}

_MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def _ext_from_mime(mime: str) -> str:
    return _MIME_TO_EXT.get(mime, "bin")
  

async def ingest_media_from_url(
    db: AsyncSession,
    *,
    tenant_id: str,
    partner_id: str,
    agent_id: str,
    url: str,
    created_by: str,
) -> MediaObject:
    
    h = hashlib.sha256()
    byte_size = 0
    tmp_path: str | None = None
    mime: str | None = None

    try:
        fd, tmp_path = tempfile.mkstemp(prefix="media_ingest_", suffix=".tmp")
        os.close(fd)

        timeout = httpx.Timeout(20.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                mime = (resp.headers.get("content-type") or "").split(";", 1)[0].strip().lower()

                if mime not in ALLOWED_MIME:
                    raise ValueError(f"unsupported mime_type: {mime}")
                
                async with await anyio.open_file(tmp_path, "wb") as f:
                    async for chunk in resp.aiter_bytes():
                        if not chunk:
                            continue
                        byte_size += len(chunk)
                        if byte_size > MAX_MEDIA_BYTES:
                            raise ValueError(f"media_too_large: > {MAX_MEDIA_BYTES} bytes")

                        h.update(chunk)
                        await f.write(chunk)

        content_hash = h.hexdigest()

        ext = _ext_from_mime(mime)

        existing = (await db.execute(select(MediaObject).where(
            MediaObject.tenant_id == tenant_id,
            MediaObject.partner_id == partner_id,
            MediaObject.agent_id == agent_id,
            MediaObject.content_hash == content_hash,
        ))).scalar_one_or_none()
        if existing:
            return existing

        storage = get_media_storage()
        stored = await storage.put_file(
            tenant_id=tenant_id,
            partner_id=partner_id,
            agent_id=agent_id,
            content_hash=content_hash,
            file_path=Path(tmp_path),
            ext=ext,
            byte_size=byte_size,
        )

        tmp_path = None

        m = MediaObject(
            id=gen_id("med"),
            tenant_id=tenant_id,
            partner_id=partner_id,
            agent_id=agent_id,
            content_hash=content_hash,
            byte_size=stored.byte_size,
            mime_type=mime,
            storage_backend=stored.backend,
            storage_key=stored.key,
            source_url=url,
            width=None,
            height=None,
            created_by=created_by,
            updated_by=created_by,
        )
        
        try:
            async with db.begin_nested():
                db.add(m)
                await db.flush()
            return m
        except IntegrityError:
            # someone else inserted same owner+hash; just fetch winner
            winner = (await db.execute(
                select(MediaObject).where(
                    MediaObject.tenant_id == tenant_id,
                    MediaObject.partner_id == partner_id,
                    MediaObject.agent_id == agent_id,
                    MediaObject.content_hash == content_hash,
                )
            )).scalar_one()
            return winner
        
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass