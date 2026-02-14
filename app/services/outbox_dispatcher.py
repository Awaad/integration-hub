from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxEvent
from worker.celery_app import celery


@dataclass(frozen=True)
class OutboxDispatchConfig:
    batch_size: int = 200
    lease_seconds: int = 600  
    queue: str = "outbox"
    max_attempts: int = 25


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def claim_outbox_event_ids(
    db: AsyncSession, *, cfg: OutboxDispatchConfig
) -> tuple[str, list[str]]:
    """
    Claims due pending events or stale processing events.
    Returns (lease_id, ids).
    """

    now = utcnow()
    lease_id = uuid.uuid4().hex
    lease_expires = now + timedelta(seconds=cfg.lease_seconds)

    stmt = (
        select(OutboxEvent.id, OutboxEvent.attempts)
        .where(
            OutboxEvent.dead_lettered_at.is_(None),
            OutboxEvent.attempts < cfg.max_attempts,
            or_(
                # due pending
                (
                    (OutboxEvent.status == "pending")
                    & (
                        or_(
                            OutboxEvent.next_retry_at.is_(None),
                            OutboxEvent.next_retry_at <= now,
                        )
                    )
                ),
                # stale lease reclaim
                (
                    (OutboxEvent.status == "processing")
                    & (OutboxEvent.lease_expires_at.is_not(None))
                    & (OutboxEvent.lease_expires_at <= now)
                ),
            ),
        )
        .order_by(
            OutboxEvent.next_retry_at.asc().nullsfirst(),
            OutboxEvent.created_at.asc(),
        )
        .with_for_update(skip_locked=True)
        .limit(cfg.batch_size)
    )

    rows = (await db.execute(stmt)).all()
    if not rows:
        return lease_id, []

    ids = [rid for (rid, _) in rows]

    await db.execute(
        update(OutboxEvent)
        .where(OutboxEvent.id.in_(ids))
        .values(
            status="processing",
            lease_id=lease_id,
            lease_expires_at=lease_expires,
            processing_started_at=now,
            attempts=OutboxEvent.attempts + 1,
            updated_at=now,
        )
    )

    return lease_id, ids


async def dispatch_outbox(db: AsyncSession, *, cfg: OutboxDispatchConfig) -> int:
    lease_id, ids = await claim_outbox_event_ids(db, cfg=cfg)
    if not ids:
        return 0

    for outbox_id in ids:
        celery.send_task(
            "worker.tasks.process_outbox_event",
            args=[outbox_id, lease_id],
            queue=cfg.queue,
        )

    return len(ids)