from __future__ import annotations
from urllib.parse import urlencode
import time
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_json
from app.core.db import get_db
from app.core.media_signing import sign_media_url
from app.models.media_object import MediaObject
from app.models.partner_public_token import PartnerPublicToken
from app.services.auth import Actor, get_actor  

router = APIRouter()


@router.get("/media/{media_id}/signed-url")
async def get_signed_media_url(
    media_id: str,
    expires_in: int = Query(default=3600, ge=60, le=7 * 24 * 3600),
    variant: str = Query(default="orig"),
    actor: Actor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Load media and enforce tenant+partner
    m = (
        await db.execute(
            select(MediaObject).where(
                MediaObject.id == media_id,
                MediaObject.tenant_id == actor.tenant_id,
                MediaObject.partner_id == actor.partner_id,
            )
        )
    ).scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Media not found")

    # Cross-agent protection
    if actor.role == "agent" and actor.agent_id != m.agent_id:
        raise HTTPException(status_code=403, detail="Agent cannot access another agent's media")

    tok = (
        await db.execute(
            select(PartnerPublicToken).where(
                PartnerPublicToken.tenant_id == actor.tenant_id,
                PartnerPublicToken.partner_id == actor.partner_id,
                PartnerPublicToken.scope == "media",
                PartnerPublicToken.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not tok:
        raise HTTPException(status_code=409, detail="No active media public token. Rotate one first.")

    secret_payload = decrypt_json(tok.token_ciphertext)
    signing_secret = secret_payload.get("signing_secret")
    
    if not signing_secret:
        raise HTTPException(status_code=500, detail="Invalid token configuration")

    expires = int(time.time()) + int(expires_in)
    variant = variant.strip().lower()
    
    sig = sign_media_url(
        secret=signing_secret,
        media_id=m.id,
        expires=expires,
        variant=variant,
        kid=tok.id,
    ).sig

    
    base = settings.public_base_url.rstrip("/")
    qs = urlencode({
        "expires": expires,
        "variant": variant,
        "kid": tok.id,
        "sig": sig,
    })

    url = f"{base}/public/media/{m.id}?{qs}"

    return {
        "media_id": m.id,
        "variant": variant,
        "expires": expires,
        "kid": tok.id,
        "url": url,
    }
