from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import AdapterContext
from app.adapters.registry import get_adapter
from app.core.db import get_db
from app.models.agent import Agent
from app.schemas.adapter_preview import AdapterPreviewRequest, AdapterPreviewResponse
from app.services.auth import Actor, require_partner_admin
from app.services.canonical_validate import validate_and_normalize_canonical

router = APIRouter()

@router.post("/partners/{partner_id}/adapters/{partner_key}/preview", response_model=AdapterPreviewResponse)
async def preview_adapter_mapping(
    partner_id: str,
    partner_key: str,
    body: AdapterPreviewRequest,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
) -> AdapterPreviewResponse:
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    # If agent_id is provided, verify it belongs to this tenant+partner.
    agent_id = body.agent_id
    if agent_id:
        a = (await db.execute(select(Agent).where(
            Agent.id == agent_id,
            Agent.partner_id == partner_id,
            Agent.tenant_id == actor.tenant_id,
        ))).scalar_one_or_none()
        if not a:
            raise HTTPException(status_code=404, detail="Agent not found")

    adapter = get_adapter(partner_key, body.adapter_version)

    partner_key = partner_key.lower().strip()
    
    ctx = AdapterContext(
        tenant_id=actor.tenant_id,
        partner_id=partner_id,
        agent_id=agent_id,
        source_listing_id=body.source_listing_id,
    )

    mapped = adapter.map_listing(payload=body.payload, ctx=ctx)
    if not mapped.ok or not mapped.canonical:
        return AdapterPreviewResponse(
            ok=False,
            partner_key=partner_key,
            canonical_schema="canonical.listing",
            canonical_schema_version="1.0",
            canonical=None,
            normalized=None,
            content_hash=None,
            adapter_version=adapter.version,
            errors=mapped.errors,
        )

    canonical_payload = dict(mapped.canonical)
    canonical_payload.setdefault("schema", "canonical.listing")
    canonical_payload.setdefault("schema_version", "1.0")

    # For preview we don't assign hub listing ids; we allow adapters to provide canonical_id if they want.
    res = validate_and_normalize_canonical(
        schema=canonical_payload.get("schema", "canonical.listing"),
        schema_version=canonical_payload.get("schema_version", "1.0"),
        payload=canonical_payload,
    )

    if not res.ok:
        return AdapterPreviewResponse(
            ok=False,
            partner_key=partner_key,
            canonical_schema=canonical_payload.get("schema", "canonical.listing"),
            canonical_schema_version=canonical_payload.get("schema_version", "1.0"),
            canonical=canonical_payload,
            normalized=None,
            content_hash=None,
            errors=res.errors,
        )

    return AdapterPreviewResponse(
        ok=True,
        partner_key=partner_key,
        canonical_schema=canonical_payload.get("schema", "canonical.listing"),
        canonical_schema_version=canonical_payload.get("schema_version", "1.0"),
        canonical=canonical_payload,
        normalized=res.normalized,
        content_hash="sha256:" + res.content_hash if res.content_hash else None,
        adapter_version=adapter.version,
        errors=[],
    )
