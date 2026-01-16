from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.ingest import IngestListingRequest, IngestListingResponse
from app.services.auth import Actor, require_api_key  
from app.services.ingest import ingest_listing, IngestError

from app.models.outbox import OutboxEvent

router = APIRouter()


@router.post("/ingest/{partner_key}/listings/{source_listing_id}", response_model=IngestListingResponse)
async def ingest_listing_endpoint(
    partner_key: str,
    source_listing_id: str,
    body: IngestListingRequest,
    actor: Actor = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> IngestListingResponse:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")

    # Determine owner agent_id
    if actor.agent_id:
        # agent API key: cannot override agent_id
        if body.agent_id and body.agent_id != actor.agent_id:
            raise HTTPException(status_code=403, detail="Agent cannot ingest for another agent")
        agent_id = actor.agent_id
    else:
        # partner_admin: must specify agent_id
        if not body.agent_id:
            raise HTTPException(status_code=422, detail="agent_id is required for partner_admin ingest")
        agent_id = body.agent_id

    allow_override = (actor.role == "partner_admin")
    try:
        listing, material_change, ingest_run_id, used_version = await ingest_listing(
            db=db,
            tenant_id=actor.tenant_id,
            partner_id=actor.partner_id,
            agent_id=agent_id,
            partner_key=partner_key,
            source_listing_id=source_listing_id,
            idempotency_key=idempotency_key,
            partner_payload=body.payload,
            adapter_version=body.adapter_version,
            allow_adapter_override=allow_override,
        )
    except IngestError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    # Emit outbox if material change - keeps noise down
    if material_change:
        db.add(OutboxEvent(
            tenant_id=listing.tenant_id,
            partner_id=listing.partner_id,
            aggregate_type="listing",
            aggregate_id=listing.id,
            event_type="listing.upserted",
            payload={"listing_id": listing.id},
            status="pending",
            created_by="ingest",
            updated_by="ingest",
        ))

    await db.commit()

    return IngestListingResponse(
        listing_id=listing.id,
        source_listing_id=source_listing_id,
        schema=listing.schema,
        schema_version=listing.schema_version,
        content_hash=listing.content_hash,
        material_change=material_change,
        ingest_run_id=ingest_run_id,
    )
