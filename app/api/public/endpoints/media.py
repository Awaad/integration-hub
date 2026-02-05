from __future__ import annotations

import time
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import FileResponse

from app.core.crypto import decrypt_json
from app.core.db import get_db
from app.core.media_signing import verify_media_sig
from app.models.media_object import MediaObject
from app.models.partner_public_token import PartnerPublicToken
from app.services.media_storage.provider import get_media_storage

router = APIRouter()


@router.get("/media/{media_id}")
async def public_get_media(
    media_id: str,
    expires: int = Query(...),
    variant: str = Query("orig"),
    kid: str = Query(...),
    sig: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    # basic expiry check first
    now = int(time.time())
    if expires < now:
        raise HTTPException(status_code=403, detail="URL expired")

    m = (
        await db.execute(select(MediaObject).where(MediaObject.id == media_id))
    ).scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Media not found")
    

    tok = (
        await db.execute(
            select(PartnerPublicToken).where(
                PartnerPublicToken.id == kid,
                PartnerPublicToken.tenant_id == m.tenant_id,
                PartnerPublicToken.partner_id == m.partner_id,
                PartnerPublicToken.scope == "media",
                PartnerPublicToken.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not tok:
        raise HTTPException(status_code=403, detail="Invalid token")

    payload = decrypt_json(tok.token_ciphertext)
    signing_secret = payload.get("signing_secret")
    if not signing_secret:
        raise HTTPException(status_code=403, detail="Invalid token")


    # enforce token row and media belong to same tenant+partner
    if m.tenant_id != tok.tenant_id or m.partner_id != tok.partner_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    ok = verify_media_sig(
        secret=signing_secret,
        media_id=media_id,
        expires=expires,
        variant=variant,
        kid=kid,
        sig=sig,
    )
    if not ok:
        raise HTTPException(status_code=403, detail="Bad signature")

    # local serving (backend=local)
    if m.storage_backend != "local":
        raise HTTPException(status_code=501, detail="Unsupported storage backend")

    storage = get_media_storage()
    file_path = storage.resolve_local_path(backend=m.storage_backend, key=m.storage_key)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")


    ttl = max(0, min(expires - now, 7 * 24 * 3600))
    
    return FileResponse(
        path=str(file_path),
        media_type=m.mime_type,
        filename=file_path.name,
        headers={
            # tune later; for now allow CDN caching if URLs are long-lived
            "Cache-Control": f"public, max-age={ttl}, immutable",
        },
    )
