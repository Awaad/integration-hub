from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.core.db import get_db
from app.models.ingest_run import IngestRun
from app.services.auth import Actor, require_partner_admin
from app.adapters.base import AdapterContext
from app.adapters.registry import get_adapter
from app.services.listings import normalize_listing_payload_or_raise
from app.schemas.ingest_replay import IngestReplayResponse
from app.services.ingest import ingest_listing, IngestError

router = APIRouter()

@router.post("/partners/{partner_id}/ingest-runs/{ingest_run_id}/replay", response_model=IngestReplayResponse)
async def replay_ingest_run(
    partner_id: str,
    ingest_run_id: str,
    persist: bool = Query(default=False),
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
) -> IngestReplayResponse:
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    run = (await db.execute(select(IngestRun).where(
        IngestRun.id == ingest_run_id,
        IngestRun.tenant_id == actor.tenant_id,
        IngestRun.partner_id == partner_id,
    ))).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Ingest run not found")

    # If persist=true, create a new ingest run and optionally upsert listing/outbox again
    if persist:
        new_idem = f"replay:{ingest_run_id}:{uuid.uuid4().hex}"
        try:
            listing, new_run_id, used_version = await ingest_listing(
                db=db,
                tenant_id=run.tenant_id,
                partner_id=run.partner_id,
                agent_id=run.agent_id,
                partner_key=run.partner_key,
                source_listing_id=run.source_listing_id,
                idempotency_key=new_idem,
                partner_payload=run.raw_payload,  # already redacted, but fine
                adapter_version=run.adapter_version,
                allow_adapter_override=True,  # partner_admin replay
            )
        except IngestError as e:
            raise HTTPException(status_code=e.status_code, detail=e.detail)

        await db.commit()
        return IngestReplayResponse(
            ok=True,
            ingest_run_id=ingest_run_id,
            replay_ingest_run_id=new_run_id,
            adapter_version=used_version,
            normalized=listing.payload if listing else None,
            content_hash=listing.content_hash if listing else None,
            errors=[],
        )

    # Otherwise: dry-run replay (no DB writes)
    adapter = get_adapter(run.partner_key, run.adapter_version)
    ctx = AdapterContext(
        tenant_id=run.tenant_id,
        partner_id=run.partner_id,
        agent_id=run.agent_id,
        source_listing_id=run.source_listing_id,
    )
    mapped = adapter.map_listing(payload=run.raw_payload, ctx=ctx)
    if not mapped.ok or not mapped.canonical:
        return IngestReplayResponse(
            ok=False,
            ingest_run_id=ingest_run_id,
            replay_ingest_run_id=None,
            adapter_version=run.adapter_version,
            normalized=None,
            content_hash=None,
            errors=mapped.errors,
        )

    canonical_payload = dict(mapped.canonical)
    canonical_payload["schema"] = "canonical.listing"
    canonical_payload["schema_version"] = "1.0"
    canonical_payload["source_listing_id"] = run.source_listing_id
    # In dry-run, we cannot know the hub listing id without mapping lookup,
    # so we do not force canonical_id here. Validation should still mostly work.

    try:
        normalized, content_hash = normalize_listing_payload_or_raise(
            schema="canonical.listing",
            schema_version="1.0",
            incoming_payload=canonical_payload,
        )
    except HTTPException as exc:
        detail = getattr(exc, "detail", str(exc))
        errors = detail["errors"] if isinstance(detail, dict) and isinstance(detail.get("errors"), list) else [{"type": "error", "message": str(detail)}]
        return IngestReplayResponse(
            ok=False,
            ingest_run_id=ingest_run_id,
            replay_ingest_run_id=None,
            adapter_version=run.adapter_version,
            normalized=None,
            content_hash=None,
            errors=errors,
        )

    return IngestReplayResponse(
        ok=True,
        ingest_run_id=ingest_run_id,
        replay_ingest_run_id=None,
        adapter_version=run.adapter_version,
        normalized=normalized,
        content_hash=content_hash,
        errors=[],
    )
