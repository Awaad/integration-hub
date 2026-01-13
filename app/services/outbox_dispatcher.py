from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.models.outbox import OutboxEvent
from worker.tasks import process_outbox_event


async def claim_outbox_events(db: AsyncSession, batch_size: int = 100) -> list[OutboxEvent]:
    # Claim pending outbox events safely using FOR UPDATE SKIP LOCKED.
    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.status == "pending")
        .order_by(OutboxEvent.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(batch_size)
    )
    events = (await db.execute(stmt)).scalars().all()
    if not events:
        return []

    ids = [e.id for e in events]
    await db.execute(
        update(OutboxEvent)
        .where(OutboxEvent.id.in_(ids))
        .values(status="processing", processing_started_at=func.now(), attempts=OutboxEvent.attempts + 1)
    )
    await db.flush()
    return events


async def dispatch_outbox(db: AsyncSession, batch_size: int = 100) -> int:
    events = await claim_outbox_events(db, batch_size=batch_size)
    for ev in events:
        process_outbox_event.delay(ev.id)
    await db.commit()
    return len(events)