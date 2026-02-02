from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert

from app.core.db import get_db
from app.core.ids import gen_id
from app.models.listing import Listing
from app.models.listing_media import ListingMedia
from app.schemas.media import MediaIngestUrlIn, MediaIngestUrlOut, MediaObjectOut, ListingMediaOut
from app.services.auth import Actor, get_actor
from app.services.idempotency import (
    get_or_reserve_idempotency,
    require_idempotency_key,
    store_idempotency_response,
)
from app.services.media_ingest import ingest_media_from_url

router = APIRouter()


def _enforce_listing_access(actor: Actor, listing: Listing) -> None:
    if actor.partner_id != listing.partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")
    if actor.role == "agent" and actor.agent_id != listing.agent_id:
        raise HTTPException(status_code=403, detail="Agent cannot act for another agent")


@router.post(
    "/listings/{listing_id}/media:ingest-url",
    response_model=MediaIngestUrlOut,
)
async def ingest_listing_media_from_url(
    listing_id: str,
    payload: MediaIngestUrlIn,
    request: Request,
    actor: Actor = Depends(get_actor),
    idempotency_key: str = Depends(require_idempotency_key),
    db: AsyncSession = Depends(get_db),
) -> MediaIngestUrlOut:
    # Load listing and enforce scope
    stmt = select(Listing).where(
        Listing.id == listing_id,
        Listing.tenant_id == actor.tenant_id,
        Listing.partner_id == actor.partner_id,
        Listing.is_active.is_(True),
    )
    listing = (await db.execute(stmt)).scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    _enforce_listing_access(actor, listing)

    # Idempotency
    body_dict = payload.model_dump()
    existing_idm, _ = await get_or_reserve_idempotency(
        db=db,
        actor=actor,
        idempotency_key=idempotency_key,
        request_path=str(request.url.path),
        request_body=body_dict,
    )
    if existing_idm:
        return MediaIngestUrlOut(**existing_idm.response)

    
    media = await ingest_media_from_url(
        db=db,
        tenant_id=listing.tenant_id,
        partner_id=listing.partner_id,
        agent_id=listing.agent_id,
        url=str(payload.url),
        created_by=actor.api_key_id,
    )


    # Upsert listing_media link (select then update/insert)
    link_stmt = select(ListingMedia).where(
        ListingMedia.tenant_id == listing.tenant_id,
        ListingMedia.partner_id == listing.partner_id,
        ListingMedia.agent_id == listing.agent_id,
        ListingMedia.listing_id == listing.id,
        ListingMedia.media_id == media.id,
    )
    try:
        async with db.begin_nested():
            
            if payload.is_primary:
                await db.execute(
                    update(ListingMedia)
                    .where(
                        ListingMedia.tenant_id == listing.tenant_id,
                        ListingMedia.partner_id == listing.partner_id,
                        ListingMedia.agent_id == listing.agent_id,
                        ListingMedia.listing_id == listing.id,
                        ListingMedia.is_primary.is_(True),
                    )
                    .values(
                        is_primary=False,
                        updated_by=actor.api_key_id,
                        updated_at=func.now(),
                    )
                )

            upsert_stmt = (
                insert(ListingMedia)
                .values(
                    id=gen_id("lmd"),
                    tenant_id=listing.tenant_id,
                    partner_id=listing.partner_id,
                    agent_id=listing.agent_id,
                    listing_id=listing.id,
                    media_id=media.id,
                    type=payload.type,
                    order_index=payload.order_index,
                    caption=payload.caption,
                    is_primary=payload.is_primary,
                    created_by=actor.api_key_id,
                    updated_by=actor.api_key_id,
                )
                .on_conflict_do_update(
                    index_elements=["tenant_id", "partner_id", "agent_id", "listing_id", "media_id"],
                    set_={
                        "type": payload.type,
                        "order_index": payload.order_index,
                        "caption": payload.caption,
                        "is_primary": payload.is_primary,
                        "updated_by": actor.api_key_id,
                        "updated_at": func.now(),
                    },
                )
                .returning(ListingMedia)
            )

            link = (await db.execute(upsert_stmt)).scalar_one()
            
            await db.flush()

    except IntegrityError:
        # savepoint auto-rolls back; do NOT rollback whole transaction
        # Re-fetch whatever exists now (someone else won)
        link = (await db.execute(link_stmt)).scalar_one()


    resp = MediaIngestUrlOut(
        media=MediaObjectOut(
            id=media.id,
            tenant_id=media.tenant_id,
            partner_id=media.partner_id,
            agent_id=media.agent_id,
            content_hash=media.content_hash,
            byte_size=media.byte_size,
            mime_type=media.mime_type,
            storage_backend=media.storage_backend,
            storage_key=media.storage_key,
            source_url=media.source_url,
            width=media.width,
            height=media.height,
            created_by=media.created_by,
            updated_by=media.updated_by,
        ),
        link=ListingMediaOut(
            id=link.id,
            tenant_id=link.tenant_id,
            partner_id=link.partner_id,
            agent_id=link.agent_id,
            listing_id=link.listing_id,
            media_id=link.media_id,
            type=link.type,
            order_index=link.order_index,
            caption=link.caption,
            is_primary=link.is_primary,
            created_by=link.created_by,
            updated_by=link.updated_by,
        ),
    )

    await store_idempotency_response(
        db=db,
        actor=actor,
        idempotency_key=idempotency_key,
        response=resp.model_dump(),
    )

    await db.commit()
    return resp
