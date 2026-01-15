from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.connectors.registry import get_connector
from app.core.crypto import decrypt_json
from app.models.agent_credential import AgentCredential
from app.models.delivery import Delivery, DeliveryAttempt
from app.models.listing import Listing

from datetime import datetime, timedelta, timezone
from app.services.retry import compute_backoff_seconds


MAX_DELIVERY_ATTEMPTS = 5


async def publish_delivery(db: AsyncSession, delivery_id: str) -> None:
    d = (await db.execute(select(Delivery).where(Delivery.id == delivery_id))).scalar_one_or_none()
    if not d:
        return

    if d.dead_lettered_at is not None:
        return

    listing = (await db.execute(select(Listing).where(Listing.id == d.listing_id))).scalar_one()

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
        return
    
    # count the attempt upfront
    d.attempts += 1
    d.last_attempt_at = func.now()

    if d.attempts >= MAX_DELIVERY_ATTEMPTS:
        d.status = "dead_lettered"
        d.dead_lettered_at = func.now()
        d.status_detail = "max attempts exceeded"
        return

    secrets = decrypt_json(cred.secret_ciphertext)
    connector = get_connector(d.destination)

    result = await connector.publish_listing(
        listing={"id": listing.id, "payload": listing.payload, "schema": listing.schema},
        credentials=secrets,
    )

    now = datetime.now(timezone.utc)

    if d.status == "success":
        d.next_retry_at = None

    elif d.status == "failed" and d.dead_lettered_at is None:
        # retryable failures get a schedule
        seconds = compute_backoff_seconds(d.attempts)
        d.next_retry_at = now + timedelta(seconds=seconds)

    elif d.status == "dead_lettered":
        d.next_retry_at = None


    db.add(DeliveryAttempt(
        delivery_id=d.id,
        status="success" if result.ok else "failed",
        request={"listing_id": listing.id, "content_hash": listing.content_hash, "destination": d.destination},
        response=result.detail or {},
        error_code=result.error_code,
        error_message=result.error_message,
    ))

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

