from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.models.outbox import OutboxEvent
from worker.tasks import process_outbox_event


async def dispatch_outbox(db: AsyncSession, batch_size: int = 100) -> int:
    # Claim pending events (simple approach for Phase 0).
    # In Phase 1/2 we’ll use FOR UPDATE SKIP LOCKED claim semantics.
    stmt = select(OutboxEvent).where(OutboxEvent.status == "pending").limit(batch_size)
    events = (await db.execute(stmt)).scalars().all()

    count = 0
    for ev in events:
        # Mark as sent once enqueued (Celery offers at-least-once enqueue; outbox makes this recoverable)
        await db.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == ev.id)
            .values(status="sent", sent_at=func.now(), attempts=OutboxEvent.attempts + 1)
        )
        process_outbox_event.delay(ev.id)
        count += 1

    await db.commit()
    return count
