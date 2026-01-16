from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.agent import Agent
from app.models.listing import Listing
from app.models.outbox import OutboxEvent
from app.schemas.listing import ListingOut, ListingUpsert
from app.services.auth import Actor, get_actor

from app.services.idempotency import (
    get_or_reserve_idempotency, 
    require_idempotency_key, 
    store_idempotency_response,
    )
from app.services.listings import upsert_listing_record

router = APIRouter()


async def _assert_agent_exists(db: AsyncSession, tenant_id: str, partner_id: str, agent_id: str) -> None:
    stmt = select(Agent).where(
        Agent.id == agent_id,
        Agent.partner_id == partner_id,
        Agent.tenant_id == tenant_id,
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Agent not found")


def _enforce_actor_scope(actor: Actor, partner_id: str, agent_id: str) -> None:
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")
    if actor.role == "agent" and actor.agent_id != agent_id:
        raise HTTPException(status_code=403, detail="Agent cannot act for another agent")




@router.put(
    "/partners/{partner_id}/agents/{agent_id}/listings/{source_listing_id}",
    response_model=ListingOut,
)
async def upsert_listing(
    partner_id: str,
    agent_id: str,
    source_listing_id: str,
    payload: ListingUpsert,
    request: Request,
    actor: Actor = Depends(get_actor),
    idempotency_key: str = Depends(require_idempotency_key),
    db: AsyncSession = Depends(get_db),
) -> ListingOut:
    _enforce_actor_scope(actor, partner_id, agent_id)
    await _assert_agent_exists(db, actor.tenant_id, partner_id, agent_id)

    
    # Use original request body for idempotency reservation checks
    body_dict = payload.model_dump()
    existing_idm, _ = await get_or_reserve_idempotency(
        db=db,
        actor=actor,
        idempotency_key=idempotency_key,
        request_path=str(request.url.path),
        request_body=body_dict,
    )
    if existing_idm:
        # Safe retry: return stored response
        return ListingOut(**existing_idm.response)

    listing = await upsert_listing_record(
        db=db,
        actor=actor,
        partner_id=partner_id,
        agent_id=agent_id,
        source_listing_id=source_listing_id,
        status=payload.status,
        schema=payload.schema,
        schema_version=payload.schema_version,
        incoming_payload=payload.payload,
    )

    resp = ListingOut(
        id=listing.id,
        tenant_id=listing.tenant_id,
        partner_id=listing.partner_id,
        agent_id=listing.agent_id,
        source_listing_id=listing.source_listing_id,
        status=listing.status,
        schema=listing.schema,
        schema_version=listing.schema_version,
        content_hash=listing.content_hash,
        payload=listing.payload,
        created_by=listing.created_by,
        updated_by=listing.updated_by,
    ).model_dump()

    await store_idempotency_response(db=db, actor=actor, idempotency_key=idempotency_key, response=resp)

    await db.commit()

    return ListingOut(**resp)


@router.get(
    "/partners/{partner_id}/agents/{agent_id}/listings",
    response_model=list[ListingOut],
)
async def list_listings(
    partner_id: str,
    agent_id: str,
    actor: Actor = Depends(get_actor),
    db: AsyncSession = Depends(get_db),
) -> list[ListingOut]:
    _enforce_actor_scope(actor, partner_id, agent_id)
    await _assert_agent_exists(db, actor.tenant_id, partner_id, agent_id)

    stmt = select(Listing).where(
        Listing.tenant_id == actor.tenant_id,
        Listing.partner_id == partner_id,
        Listing.agent_id == agent_id,
        Listing.is_active.is_(True),
    ).order_by(Listing.updated_at.desc())

    rows = (await db.execute(stmt)).scalars().all()
    return [
        ListingOut(
            id=r.id,
            tenant_id=r.tenant_id,
            partner_id=r.partner_id,
            agent_id=r.agent_id,
            source_listing_id=r.source_listing_id,
            status=r.status,
            schema=r.schema,
            schema_version=r.schema_version,
            content_hash=r.content_hash,
            payload=r.payload,
            created_by=r.created_by,
            updated_by=r.updated_by,
        )
        for r in rows
    ]


@router.delete("/partners/{partner_id}/agents/{agent_id}/listings/{source_listing_id}")
async def delete_listing(
    partner_id: str,
    agent_id: str,
    source_listing_id: str,
    actor: Actor = Depends(get_actor),
    idempotency_key: str = Depends(require_idempotency_key),
    request: Request = None,  # FastAPI injects Request if included; keep consistent with upsert
    db: AsyncSession = Depends(get_db),
) -> dict:
    _enforce_actor_scope(actor, partner_id, agent_id)
    await _assert_agent_exists(db, actor.tenant_id, partner_id, agent_id)

    body_dict = {"op": "delete", "source_listing_id": source_listing_id}
    existing_idm, _ = await get_or_reserve_idempotency(
        db=db,
        actor=actor,
        idempotency_key=idempotency_key,
        request_path=str(request.url.path),
        request_body=body_dict,
    )
    if existing_idm and existing_idm.response:
        return existing_idm.response

    stmt = select(Listing).where(
        Listing.tenant_id == actor.tenant_id,
        Listing.partner_id == partner_id,
        Listing.agent_id == agent_id,
        Listing.source_listing_id == source_listing_id,
        Listing.is_active.is_(True),
    )
    listing = (await db.execute(stmt)).scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    listing.is_active = False
    listing.status = "archived"
    listing.updated_by = actor.api_key_id

    db.add(
        OutboxEvent(
            aggregate_type="listing",
            aggregate_id=listing.id,
            event_type="listing.deleted",
            payload={
                "tenant_id": actor.tenant_id,
                "partner_id": partner_id,
                "agent_id": agent_id,
                "listing_id": listing.id,
                "source_listing_id": source_listing_id,
            },
            status="pending",
        )
    )

    resp = {"status": "deleted", "listing_id": listing.id}
    await store_idempotency_response(db=db, actor=actor, idempotency_key=idempotency_key, response=resp)
    await db.commit()
    return resp

