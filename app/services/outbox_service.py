from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxEvent


async def enqueue_outbox_event(
    db: AsyncSession,
    *,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict,
    dedupe_key: str | None = None,
    actor_id: str = "system",
) -> bool:
    """
    Enqueue event safely.
    Returns True if inserted.
    Returns False if dedupe conflict.
    """
    ev = OutboxEvent(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
        dedupe_key=dedupe_key,
        status="pending",
        attempts=0,
        last_error=None,
        created_by=actor_id,
        updated_by=actor_id,
    )

    try:
        async with db.begin_nested():
            db.add(ev)
            await db.flush()
        return True
    except IntegrityError:
        if dedupe_key:
            # expected duplicate
            return False
        # unexpected integrity issue
        raise