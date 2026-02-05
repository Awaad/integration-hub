from __future__ import annotations
import logging 

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.core.crypto import encrypt_json
from app.core.db import get_db
from app.core.public_tokens import generate_public_token, generate_signing_secret
from app.models.partner_public_token import PartnerPublicToken
from app.schemas.public_tokens import RotateMediaPublicTokenOut
from app.services.auth import Actor, require_partner_admin
from app.services.audit import audit


log = logging.getLogger(__name__)

router = APIRouter()


@router.post("/partners/{partner_id}/public-tokens/media:rotate", response_model=RotateMediaPublicTokenOut)
async def rotate_media_public_token(
    partner_id: str,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
) -> RotateMediaPublicTokenOut:
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")


    tok = generate_public_token()
    signing_secret = generate_signing_secret()
    cipher = encrypt_json({"v": 1, "signing_secret": signing_secret})

    row = PartnerPublicToken(
        tenant_id=actor.tenant_id,
        partner_id=partner_id,
        scope="media",
        token_prefix=tok.prefix,
        token_hash=tok.hashed,
        token_ciphertext=cipher,
        is_active=True,
        created_by=actor.api_key_id,
        updated_by=actor.api_key_id,
    )

    try:
        async with db.begin():
            # deactivate old active
            await db.execute(
                update(PartnerPublicToken)
                .where(
                    PartnerPublicToken.tenant_id == actor.tenant_id,
                    PartnerPublicToken.partner_id == partner_id,
                    PartnerPublicToken.scope == "media",
                    PartnerPublicToken.is_active.is_(True),
                )
                .values(is_active=False, rotated_at=func.now(), updated_by=actor.api_key_id)
            )
            
            db.add(row)
            await db.flush()

            await audit(
                db,
                tenant_id=actor.tenant_id,
                partner_id=partner_id,
                actor_api_key_id=actor.api_key_id,
                action="public_token.media.rotated",
                target_type="partner_public_token",
                target_id=row.id,
                detail={"token_prefix": tok.prefix},
            )

    except IntegrityError:
        # db.begin() already rolled back
        log.exception("rotate media public token failed (integrity error)")
        raise HTTPException(status_code=409, detail="Constraint violation")

    
    return RotateMediaPublicTokenOut(
        partner_id=partner_id,
        scope="media",
        token_id=row.id,  # this is the kid
        public_token=None,
        token_prefix=tok.prefix,
    )
