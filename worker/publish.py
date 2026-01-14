from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.connectors.registry import get_connector
from app.core.crypto import decrypt_json
from app.models.agent_credential import AgentCredential
from app.models.delivery import Delivery, DeliveryAttempt
from app.models.listing import Listing


MAX_DELIVERY_ATTEMPTS = 5


async def publish_to_destination(
    db: AsyncSession,
    *,
    listing: Listing,
    destination: str,
) -> None:
    # Find credential for this agent+destination
    cred = (await db.execute(
        select(AgentCredential).where(
            AgentCredential.tenant_id == listing.tenant_id,
            AgentCredential.partner_id == listing.partner_id,
            AgentCredential.agent_id == listing.agent_id,
            AgentCredential.destination == destination,
            AgentCredential.is_active.is_(True),
        )
    )).scalar_one_or_none()

    if not cred:
        # No creds -> non-retryable fail
        await _record_delivery_attempt(
            db, listing, destination,
            ok=False, retryable=False,
            error_code="NO_CREDENTIALS",
            error_message="No active credentials for destination",
            response={}
        )
        return

    secrets = decrypt_json(cred.secret_ciphertext)
    connector = get_connector(destination)

    d = (await db.execute(
        select(Delivery).where(
            Delivery.tenant_id == listing.tenant_id,
            Delivery.destination == destination,
            Delivery.listing_id == listing.id,
        )
    )).scalar_one_or_none()

    if not d:
        d = Delivery(
            tenant_id=listing.tenant_id,
            partner_id=listing.partner_id,
            agent_id=listing.agent_id,
            listing_id=listing.id,
            destination=destination,
            status="pending",
            attempts=0,
        )
        db.add(d)
        await db.flush()

    if d.dead_lettered_at is not None:
        return

    if d.attempts >= MAX_DELIVERY_ATTEMPTS:
        d.status = "dead_lettered"
        d.dead_lettered_at = func.now()
        d.status_detail = "max attempts exceeded"
        return

    result = await connector.publish_listing(
        listing={"id": listing.id, "payload": listing.payload, "schema": listing.schema},
        credentials=secrets,
    )

    d.attempts += 1
    d.last_attempt_at = func.now()

    attempt = DeliveryAttempt(
        delivery_id=d.id,
        status="success" if result.ok else "failed",
        request={"listing_id": listing.id, "content_hash": listing.content_hash, "destination": destination},
        response=result.detail or {},
        error_code=result.error_code,
        error_message=result.error_message,
    )
    db.add(attempt)

    if result.ok:
        d.status = "success"
        d.last_success_at = func.now()
        d.last_error = None
        d.status_detail = None
    else:
        d.status = "failed"
        d.last_error = result.error_message
        d.status_detail = result.error_code

        if (not result.retryable) or (d.attempts >= MAX_DELIVERY_ATTEMPTS):
            d.status = "dead_lettered"
            d.dead_lettered_at = func.now()


async def _record_delivery_attempt(
    db: AsyncSession,
    listing: Listing,
    destination: str,
    *,
    ok: bool,
    retryable: bool,
    error_code: str,
    error_message: str,
    response: dict,
) -> None:
    d = (await db.execute(
        select(Delivery).where(
            Delivery.tenant_id == listing.tenant_id,
            Delivery.destination == destination,
            Delivery.listing_id == listing.id,
        )
    )).scalar_one_or_none()

    if not d:
        d = Delivery(
            tenant_id=listing.tenant_id,
            partner_id=listing.partner_id,
            agent_id=listing.agent_id,
            listing_id=listing.id,
            destination=destination,
            status="pending",
            attempts=0,
        )
        db.add(d)
        await db.flush()

    d.attempts += 1
    d.last_attempt_at = func.now()
    d.status = "failed" if retryable else "dead_lettered"
    d.last_error = error_message
    d.status_detail = error_code
    if not retryable:
        d.dead_lettered_at = func.now()

    db.add(DeliveryAttempt(
        delivery_id=d.id,
        status="failed",
        request={"listing_id": listing.id, "destination": destination},
        response=response,
        error_code=error_code,
        error_message=error_message,
    ))
