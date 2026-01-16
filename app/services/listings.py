from __future__ import annotations

from typing import Any, Tuple

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.listing import Listing
from app.models.outbox import OutboxEvent
from app.services.auth import Actor
from app.services.canonical_validate import validate_and_normalize_canonical


def normalize_listing_payload_or_raise(
    *,
    schema: str,
    schema_version: str,
    incoming_payload: dict[str, Any],
) -> Tuple[dict[str, Any], str]:
    """
    Validate + normalize canonical payload and compute stable content hash.
    Returns (normalized_payload, content_hash_with_prefix).
    Raises HTTPException on error (400 unsupported schema, 422 validation).
    """
    res = validate_and_normalize_canonical(
        schema=schema,
        schema_version=schema_version,
        payload=incoming_payload,
    )

    if not res.ok:
        if res.errors and res.errors[0].get("type") == "schema_not_supported":
            raise HTTPException(status_code=400, detail={"errors": res.errors})
        raise HTTPException(status_code=422, detail={"errors": res.errors})

    assert res.normalized is not None
    assert res.content_hash is not None
    return res.normalized, "sha256:" + res.content_hash


async def upsert_listing_record(
    *,
    db: AsyncSession,
    actor: Actor,
    partner_id: str,
    agent_id: str,
    source_listing_id: str,
    status: str,
    schema: str,
    schema_version: str,
    incoming_payload: dict[str, Any],
) -> Listing:
    """
    Upsert Listing row + emit outbox event.
    Canonical payload is validated & normalized before storage.

    Note: Auth, agent existence, and idempotency are handled by the API layer.
    """
    normalized_payload, content_hash = normalize_listing_payload_or_raise(
        schema=schema,
        schema_version=schema_version,
        incoming_payload=incoming_payload,
    )

    stmt = select(Listing).where(
        Listing.tenant_id == actor.tenant_id,
        Listing.partner_id == partner_id,
        Listing.agent_id == agent_id,
        Listing.source_listing_id == source_listing_id,
    )
    listing = (await db.execute(stmt)).scalar_one_or_none()

    created = False
    changed = True

    if listing:
        # Determine if this is a material change. If not, avoid rewriting payload and avoid outbox noise.
        same_content = listing.content_hash == content_hash
        same_envelope = (
            listing.status == status
            and listing.schema == schema
            and listing.schema_version == schema_version
        )
        changed = not (same_content and same_envelope)

        if changed:
            listing.status = status
            listing.schema = schema
            listing.schema_version = schema_version
            listing.payload = normalized_payload
            listing.content_hash = content_hash

        # still record who touched it (even if no-op)
        listing.updated_by = actor.api_key_id
    else:
        created = True
        listing = Listing(
            tenant_id=actor.tenant_id,
            partner_id=partner_id,
            agent_id=agent_id,
            source_listing_id=source_listing_id,
            status=status,
            schema=schema,
            schema_version=schema_version,
            payload=normalized_payload,
            content_hash=content_hash,
            created_by=actor.api_key_id,
            updated_by=actor.api_key_id,
        )
        db.add(listing)

    await db.flush()

     # Emit outbox only if it was created or materially changed.
    if created or changed:
        db.add(
            OutboxEvent(
                aggregate_type="listing",
                aggregate_id=listing.id,
                event_type="listing.upserted",
                payload={
                    "tenant_id": actor.tenant_id,
                    "partner_id": partner_id,
                    "agent_id": agent_id,
                    "listing_id": listing.id,
                    "source_listing_id": source_listing_id,
                    "schema": listing.schema,
                    "schema_version": listing.schema_version,
                    "content_hash": listing.content_hash,
                },
                status="pending",
                created_by=actor.api_key_id,
                updated_by=actor.api_key_id,
            )
        )

    return listing