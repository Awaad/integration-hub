from __future__ import annotations

import time
from urllib.parse import urlencode

from starlette.responses import FileResponse, Response
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse


from app.core.crypto import decrypt_json
from app.core.db import get_db
from app.core.media_signing import verify_media_sig, sign_media_url
from app.models.media_object import MediaObject
from app.models.partner_public_token import PartnerPublicToken
from app.services.media_storage.provider import get_media_storage
from app.services.media_storage.media_variant_store import get_or_create_variant


router = APIRouter()


_ALLOWED_VARIANTS = {"orig", "thumb", "medium", "large"}
_MAX_TTL = 7 * 24 * 3600
_REDIRECT_TTL = 120


def _etag_value(etag: str) -> str:
    # Always return a quoted strong ETag value
    return f'"{etag}"'


def _if_none_match_matches(inm: str | None, etag: str) -> bool:
    if not inm:
        return False
    target = _etag_value(etag)

    # RFC: If-None-Match can be "*" or a list of etags
    inm = inm.strip()
    if inm == "*":
        return True

    parts = [p.strip() for p in inm.split(",")]
    return target in parts or etag in [p.strip('"') for p in parts]


@router.get("/media/{media_id}/r")
async def public_media_redirect(
    media_id: str,
    variant: str = Query("orig"),
    kid: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    variant = (variant or "orig").strip().lower()
    if variant not in _ALLOWED_VARIANTS:
        raise HTTPException(status_code=400, detail="Unsupported variant")

    m = (await db.execute(select(MediaObject).where(MediaObject.id == media_id))).scalar_one_or_none()
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

    expires = int(time.time()) + _REDIRECT_TTL
    sig = sign_media_url(
        secret=signing_secret,
        media_id=media_id,
        expires=expires,
        variant=variant,
        kid=kid,
    ).sig

    qs = urlencode({"expires": expires, "variant": variant, "kid": kid, "sig": sig})
    location = f"/public/media/{media_id}?{qs}"

    return RedirectResponse(
        url=location,
        status_code=307,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/media/{media_id}")
async def public_get_media(
    media_id: str,
    request: Request,
    expires: int = Query(...),
    variant: str = Query("orig"),
    kid: str = Query(...),
    sig: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    # basic expiry check first
    now = int(time.time())
    expires = int(expires)
    variant = variant.strip().lower()

    if variant not in _ALLOWED_VARIANTS:
        raise HTTPException(status_code=400, detail="Unsupported variant")

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


    storage = get_media_storage()

    if variant == "orig":
        backend = m.storage_backend
        key = m.storage_key
        mime = m.mime_type
        etag = m.content_hash 
    else:
        if m.storage_backend != "local":
            raise HTTPException(status_code=501, detail="Variants unsupported for this storage backend")
        try:
            mv = await get_or_create_variant(db, media=m, variant=variant)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        backend = mv.storage_backend
        key = mv.storage_key
        mime = mv.mime_type
        etag = mv.variant_hash
        
    file_path = storage.resolve_local_path(backend=backend, key=key)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")


    ttl = max(0, min(expires - now, _MAX_TTL))

    inm = request.headers.get("if-none-match")
    if _if_none_match_matches(inm, etag):
        return Response(
            status_code=304,
            headers={
                "ETag": _etag_value(etag),
                "Cache-Control": f"public, max-age={ttl}, immutable",
            },
        )
    
    return FileResponse(
        path=str(file_path),
        media_type=mime,
        headers={
            "ETag": _etag_value(etag),
            "Cache-Control": f"public, max-age={ttl}, immutable",
        },
    )
