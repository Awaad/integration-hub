from __future__ import annotations
from fastapi import HTTPException
from typing import Any
from app.services.listings import normalize_listing_payload_or_raise
from app.services.redaction import redact_payload
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.adapters.base import AdapterContext
from app.adapters.registry import get_adapter, default_adapter_version
from app.core.ids import gen_id
from app.models.source_listing_mapping import SourceListingMapping
from app.models.listing import Listing
from app.models.ingest_run import IngestRun


class IngestError(Exception):
    def __init__(self, status_code: int, detail: Any):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


def _extract_errors(detail: Any) -> list[dict[str, Any]]:
    """
    Normalize various error shapes into list[dict] for run.errors.
    """
    if isinstance(detail, dict) and isinstance(detail.get("errors"), list):
        return detail["errors"]
    if isinstance(detail, list):
        return detail
    return [{"type": "error", "message": str(detail)}]


async def ingest_listing(
    *,
    db: AsyncSession,
    tenant_id: str,
    partner_id: str,
    agent_id: str,
    partner_key: str,
    source_listing_id: str,
    idempotency_key: str,
    partner_payload: dict[str, Any],
    adapter_version: str | None,
    allow_adapter_override: bool,
) -> tuple[Listing | None, bool, str, str]:
    """
    Returns (listing, material_change, ingest_run_id).
    - listing may be None for idempotent replays of prior failed ingests.
    - material_change=True when content_hash changed (new outbox event is warranted).
    """
    partner_key_norm = partner_key.lower().strip()

    default_version = default_adapter_version(partner_key_norm)
    requested_version = adapter_version
    used_version = requested_version or default_version

    run = IngestRun(
        tenant_id=tenant_id,
        partner_id=partner_id,
        agent_id=agent_id,
        partner_key=partner_key_norm,
        source_listing_id=source_listing_id,
        idempotency_key=idempotency_key,
        raw_payload=redact_payload(partner_payload),
        canonical_payload=None,
        errors=[],
        status="failed", 
        listing_id=None,
        adapter_version=used_version,
    )
    db.add(run)

    # Record forbidden adapter override as a failed ingest run (keeps observability)
    if requested_version and not allow_adapter_override:
        run.errors = [{
            "type": "forbidden",
            "message": "adapter_version override not allowed",
            "requested_adapter_version": requested_version,
            "used_adapter_version": used_version,
        }]
        run.status = "failed"
        await db.flush()
        raise IngestError(403, {"errors": run.errors, "ingest_run_id": run.id})

    try:
        await db.flush()  # ensures run.id available; also enforces idempotency constraint early
    except IntegrityError:
        # Same (source_listing_id + idempotency_key) already recorded: idempotent replay
        await db.rollback()
        # Fetch and return existing outcome (idempotent semantics)
        existing = (await db.execute(select(IngestRun).where(
            IngestRun.tenant_id == tenant_id,
            IngestRun.partner_id == partner_id,
            IngestRun.partner_key == partner_key_norm,
            IngestRun.source_listing_id == source_listing_id,
            IngestRun.idempotency_key == idempotency_key,
        ))).scalar_one()

        if existing.status == "success" and existing.listing_id:
            listing = (await db.execute(select(Listing).where(Listing.id == existing.listing_id))).scalar_one()
            return listing, False, existing.id, existing.adapter_version
        
        return None, False, existing.id, existing.adapter_version

    try:
        used_version = adapter_version or default_adapter_version(partner_key_norm)
        run.adapter_version = used_version

        adapter = get_adapter(partner_key_norm, used_version)

        # adapter mapping
        ctx = AdapterContext(
            tenant_id=tenant_id, 
            partner_id=partner_id, 
            agent_id=agent_id, 
            source_listing_id=source_listing_id, 
        )
        mapped = adapter.map_listing(payload=partner_payload, ctx=ctx)

        if not mapped.ok or not mapped.canonical:

            run.errors = mapped.errors
            run.status = "failed"
            await db.flush()
            raise IngestError(422, {"errors": mapped.errors, "ingest_run_id": run.id})

        canonical_payload = dict(mapped.canonical)
        canonical_payload["schema"] = "canonical.listing"
        canonical_payload["schema_version"] = "1.0"
        # listing_id chosen via mapping table logic below, but canonical_id must match the hub listing id.
        # We'll fill canonical_id once listing_id determined.

        # resolve mapping to hub listing_id
        mapping = (await db.execute(
            select(SourceListingMapping).where(
                SourceListingMapping.tenant_id == tenant_id,
                SourceListingMapping.partner_id == partner_id,
                SourceListingMapping.partner_key == partner_key_norm,
                SourceListingMapping.source_listing_id == source_listing_id,
            )
        )).scalar_one_or_none()

        listing_id = mapping.listing_id if mapping else gen_id("lst")
        canonical_payload["canonical_id"] = listing_id
        canonical_payload["source_listing_id"] = source_listing_id

        # canonical validate+normalize (shared logic with API upsert)
        try:
            normalized_payload, content_hash = normalize_listing_payload_or_raise(
                schema="canonical.listing",
                schema_version="1.0",
                incoming_payload=canonical_payload,
            )
        except HTTPException as exc:
            # Normalize to ingest run error shape and raise IngestError
            errors = _extract_errors(getattr(exc, "detail", str(exc)))
            run.canonical_payload = canonical_payload
            run.errors = errors
            run.status = "failed"
            await db.flush()
            raise IngestError(exc.status_code, {"errors": errors, "ingest_run_id": run.id})

        run.canonical_payload = normalized_payload

        # upsert listing
        listing = (await db.execute(select(Listing).where(
            Listing.id == listing_id,
            Listing.tenant_id == tenant_id,
            Listing.partner_id == partner_id,
            Listing.agent_id == agent_id,
        ))).scalar_one_or_none()

        material_change = False

        if not listing:
            listing = Listing(
                id=listing_id,
                tenant_id=tenant_id,
                partner_id=partner_id,
                agent_id=agent_id,
                schema="canonical.listing",
                schema_version="1.0",
                payload=normalized_payload,
                content_hash=content_hash,
                status=normalized_payload.get("status", "draft"),
                created_by="ingest",
                updated_by="ingest",
            )
            db.add(listing)
            material_change = True
        else:
            if listing.content_hash != content_hash:
                material_change = True
                listing.payload = normalized_payload
                listing.content_hash = content_hash
                listing.status = normalized_payload.get("status", listing.status)
                listing.updated_by = "ingest"

        # upsert mapping
        if not mapping:
            mapping = SourceListingMapping(
                tenant_id=tenant_id,
                partner_id=partner_id,
                agent_id=agent_id,
                partner_key=partner_key_norm,
                adapter_version=used_version,
                source_listing_id=source_listing_id,
                listing_id=listing_id,
            )
            db.add(mapping)
        else:
            # Keep mapping updated with the last-used adapter version
            if mapping.adapter_version != used_version:
                mapping.adapter_version = used_version

        await db.flush()

        run.status = "success"
        run.errors = []
        run.listing_id = listing_id

        await db.flush()

        return listing, material_change, run.id, used_version

    except IngestError:
        raise
    except Exception as e:
        run.errors = [{"type": "internal_error", "message": str(e)}]
        run.status = "failed"
        await db.flush()
        raise