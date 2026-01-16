from __future__ import annotations

from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.adapters.base import AdapterContext
from app.adapters.registry import get_adapter
from app.core.ids import gen_id
from app.models.source_listing_mapping import SourceListingMapping
from app.models.listing import Listing
from app.models.ingest_run import IngestRun
from app.services.canonical_validate import validate_and_normalize_canonical


class IngestError(Exception):
    def __init__(self, status_code: int, detail: Any):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


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
) -> tuple[Listing, bool]:
    """
    Returns (listing, material_change).
    - material_change=True when content_hash changed (new outbox event is warranted).
    """
    partner_key_norm = partner_key.lower().strip()

    run = IngestRun(
        tenant_id=tenant_id,
        partner_id=partner_id,
        agent_id=agent_id,
        partner_key=partner_key_norm,
        source_listing_id=source_listing_id,
        idempotency_key=idempotency_key,
        raw_payload=partner_payload,
        canonical_payload=None,
        errors=[],
        status="failed", 
        listing_id=None,
    )
    db.add(run)

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
            return listing, False, existing.id
        return None, False, existing.id

    try:
        # adapter mapping 
        adapter = get_adapter(partner_key_norm)
        ctx = AdapterContext(tenant_id=tenant_id, partner_id=partner_id, agent_id=agent_id, source_listing_id=source_listing_id)
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

        # canonical validate+normalize
        res = validate_and_normalize_canonical(schema="canonical.listing", schema_version="1.0", payload=canonical_payload)
        if not res.ok or not res.normalized or not res.content_hash:
            run.canonical_payload = canonical_payload
            run.errors = res.errors
            run.status = "failed"
            await db.flush()
            raise IngestError(422, {"errors": res.errors, "ingest_run_id": run.id})

        run.canonical_payload = res.normalized

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
                payload=res.normalized,
                content_hash=res.content_hash,
                status=res.normalized.get("status", "draft"),
                created_by="ingest",
                updated_by="ingest",
            )
            db.add(listing)
            material_change = True
        else:
            if listing.content_hash != res.content_hash:
                material_change = True
                listing.payload = res.normalized
                listing.content_hash = res.content_hash
                listing.status = res.normalized.get("status", listing.status)
                listing.updated_by = "ingest"

        if not mapping:
            mapping = SourceListingMapping(
                tenant_id=tenant_id,
                partner_id=partner_id,
                agent_id=agent_id,
                partner_key=partner_key_norm,
                source_listing_id=source_listing_id,
                listing_id=listing_id,
            )
            db.add(mapping)

        await db.flush()

        run.status = "success"
        run.errors = []
        run.listing_id = listing_id

        await db.flush()
        return listing, material_change, run.id

    except IngestError:
        raise