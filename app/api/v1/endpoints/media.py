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

    base_values = dict(
        id=gen_id("lmd"),
        tenant_id=listing.tenant_id,
        partner_id=listing.partner_id,
        agent_id=listing.agent_id,
        listing_id=listing.id,
        media_id=media.id,
        type=payload.type,
        order_index=payload.order_index,
        caption=payload.caption,
        created_by=actor.api_key_id,
        updated_by=actor.api_key_id,
    )

    conflict_key = ["tenant_id", "partner_id", "agent_id", "listing_id", "media_id"]

    async def _upsert_link(*, is_primary: bool) -> str:
        upsert_stmt = (
            insert(ListingMedia)
            .values(**base_values, is_primary=is_primary)
            .on_conflict_do_update(
                index_elements=conflict_key,
                set_={
                    "type": payload.type,
                    "order_index": payload.order_index,
                    "caption": payload.caption,
                    "is_primary": is_primary,
                    "updated_by": actor.api_key_id,
                    "updated_at": func.now(),
                },
            )
            .returning(ListingMedia.id)
        )
        return (await db.execute(upsert_stmt)).scalar_one()

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

            link_id = await _upsert_link(is_primary=payload.is_primary)
            

        link = (
            await db.execute(select(ListingMedia).where(ListingMedia.id == link_id))
        ).scalar_one()

    except IntegrityError:
        # Savepoint rolled back automatically. See what exists now.
        link = (await db.execute(link_stmt)).scalar_one_or_none()
        if link is not None:
            pass
        elif payload.is_primary:
            # Retry: attach the media but don't fight for primary
            async with db.begin_nested():
                link_id = await _upsert_link(is_primary=False)
                await db.flush()
            link = (
                await db.execute(select(ListingMedia).where(ListingMedia.id == link_id))
            ).scalar_one()
        else:
            raise


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
        listing_id=listing.id,
        idempotency_key=idempotency_key,
        response=resp.model_dump(),
    )

    await db.commit()
    return resp
