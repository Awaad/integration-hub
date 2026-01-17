from __future__ import annotations
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.core.crypto import decrypt_json
from app.models.agent_credential import AgentCredential
from app.models.delivery import Delivery, DeliveryAttempt
from app.models.listing import Listing
from app.models.listing_external_mapping import ListingExternalMapping
from app.services.publish_service import build_projected_payload, publish_projected_payload

from app.services.retry import compute_backoff_seconds


MAX_DELIVERY_ATTEMPTS = 5


async def publish_delivery(db: AsyncSession, delivery_id: str) -> None:
    d = (await db.execute(select(Delivery).where(Delivery.id == delivery_id))).scalar_one_or_none()
    if not d or d.dead_lettered_at is not None:
        return

    listing = (await db.execute(select(Listing).where(Listing.id == d.listing_id))).scalar_one()

    mapping = (await db.execute(
        select(ListingExternalMapping).where(
            ListingExternalMapping.tenant_id == d.tenant_id,
            ListingExternalMapping.destination == d.destination,
            ListingExternalMapping.listing_id == listing.id,
        )
    )).scalar_one_or_none()

    # SKIP if already synced same hash (regardless of current status)
    if mapping and mapping.last_synced_hash == listing.content_hash:
        d.status = "success"
        d.next_retry_at = None
        d.last_error = None
        d.status_detail = None
        d.last_success_at = func.now()
        return

    # Credentials by agent+destination
    cred = (await db.execute(
        select(AgentCredential).where(
            AgentCredential.tenant_id == d.tenant_id,
            AgentCredential.partner_id == d.partner_id,
            AgentCredential.agent_id == d.agent_id,
            AgentCredential.destination == d.destination,
            AgentCredential.is_active.is_(True),
        )
    )).scalar_one_or_none()

    if not cred:
        await _record_attempt_failure(
            db, d,
            error_code="NO_CREDENTIALS",
            error_message="No active credentials for destination",
            retryable=False,
        )
        d.next_retry_at = None
        return

    if d.attempts >= MAX_DELIVERY_ATTEMPTS:
        d.status = "dead_lettered"
        d.dead_lettered_at = func.now()
        d.status_detail = "max attempts exceeded"
        d.next_retry_at = None
        return


    secrets = decrypt_json(cred.secret_ciphertext)
    
     # Build projected payload + current external_listing_id (if any)
    projected_payload, external_listing_id = await build_projected_payload(db, delivery=d)

    # Publish via destination connector
    result = await publish_projected_payload(
        destination=d.destination,
        payload=projected_payload,
        credentials=secrets,
    )


    d.attempts += 1
    d.last_attempt_at = func.now()

    db.add(DeliveryAttempt(
        delivery_id=d.id,
        status="success" if result.ok else "failed",
        request={"listing_id": listing.id, "content_hash": listing.content_hash, "destination": d.destination, "external_listing_id": external_listing_id,},
        response=result.detail or {},
        error_code=getattr(result, "error_code", None),
        error_message=getattr(result, "error_message", None),
    ))

    now = datetime.now(timezone.utc)

    if result.ok:
        if not mapping:
            mapping = ListingExternalMapping(
                tenant_id=d.tenant_id,
                partner_id=d.partner_id,
                agent_id=d.agent_id,
                listing_id=listing.id,
                destination=d.destination,
                external_listing_id=getattr(result, "external_id", None) or external_listing_id,
                last_synced_hash=listing.content_hash,
                metadata={},
            )
            db.add(mapping)
        else:
            ext_id = getattr(result, "external_id", None)
            if ext_id:
                mapping.external_listing_id = ext_id
            mapping.last_synced_hash = listing.content_hash

        d.status = "success"
        d.last_success_at = func.now()
        d.last_error = None
        d.status_detail = None
        d.next_retry_at = None
        return
    
    # Failure
    d.status = "failed"
    d.last_error = getattr(result, "error_message", None)
    d.status_detail = getattr(result, "error_code", None)

    retryable = bool(getattr(result, "retryable", False))
    if (not retryable) or (d.attempts >= MAX_DELIVERY_ATTEMPTS):
        d.status = "dead_lettered"
        d.dead_lettered_at = func.now()
        d.next_retry_at = None
        return

    # retryable scheduling
    seconds = compute_backoff_seconds(d.attempts)
    d.next_retry_at = now + timedelta(seconds=seconds)
    

async def _record_attempt_failure(db: AsyncSession, d: Delivery, *, error_code: str, error_message: str, retryable: bool) -> None:
    d.attempts += 1
    d.last_attempt_at = func.now()
    d.last_error = error_message
    d.status_detail = error_code

    db.add(DeliveryAttempt(
        delivery_id=d.id,
        status="failed",
        request={"delivery_id": d.id, "destination": d.destination},
        response={},
        error_code=error_code,
        error_message=error_message,
    ))

    if retryable:
        d.status = "failed"
    else:
        d.status = "dead_lettered"
        d.dead_lettered_at = func.now()

