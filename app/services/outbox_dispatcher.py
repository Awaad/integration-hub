from datetime import timedelta
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.models.outbox import OutboxEvent
from worker.tasks import process_outbox_event
from worker.celery_app import celery


async def requeue_expired_leases(db: AsyncSession) -> int:
    result = await db.execute(
        update(OutboxEvent)
        .where(
            OutboxEvent.status == "processing",
            OutboxEvent.lease_expires_at.is_not(None),
            OutboxEvent.lease_expires_at < func.now(),
        )
        .values(
            status="pending",
            lease_id=None,
            lease_expires_at=None,
            processing_started_at=None,
            last_error="requeued: lease expired",
        )
    )
    return int(result.rowcount or 0)



async def claim_outbox_event_ids(db: AsyncSession, batch_size: int = 100, lease_minutes: int = 10) -> tuple[str, list[str]]:

    lease_id = uuid.uuid4().hex
    expires_at = func.now() + timedelta(minutes=lease_minutes)
    
    # Lock and select pending rows
    stmt = (
        select(OutboxEvent.id)
        .where(OutboxEvent.status == "pending")
        .order_by(OutboxEvent.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(batch_size)
    )
    ids = (await db.execute(stmt)).scalars().all()
    if not ids:
        return lease_id, []

    await db.execute(
        update(OutboxEvent)
        .where(OutboxEvent.id.in_(ids))
        .values(status="processing", processing_started_at=func.now(), attempts=OutboxEvent.attempts + 1, last_error=None, lease_id=lease_id, lease_expires_at=expires_at,)
    )
    await db.flush()
    return lease_id, ids


async def dispatch_outbox(db: AsyncSession, batch_size: int = 100, lease_minutes: int = 10) -> int:
    # reclaim expired leases
    await requeue_expired_leases(db)
   
    lease_id, ids = await claim_outbox_event_ids(db, batch_size=batch_size, lease_minutes=lease_minutes)
   
    # Commit before enqueue so workers can read status/rows
    await db.commit()

    if not ids:
        return 0
    
    failed: list[tuple[str, str]] = []
    dispatched = 0

    for outbox_id in ids:
        try:
            celery.send_task("worker.tasks.process_outbox_event", args=[outbox_id, lease_id], queue="outbox")
            dispatched += 1
        except Exception as e:
            failed.append((outbox_id, f"{type(e).__name__}: {e}"))

    # if enqueue fails, return those items to pending (batch)
    if failed:
        # Use a new DB transaction
        for outbox_id, msg in failed:
            await db.execute(
                update(OutboxEvent)
                .where(OutboxEvent.id == outbox_id, OutboxEvent.lease_id == lease_id)
                .values(status="pending", lease_id=None, lease_expires_at=None, processing_started_at=None, last_error=f"enqueue failed: {msg}")
            )
        await db.commit()

    return dispatched