import asyncio
import logging
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.sql import func

from app.core.config import settings
from app.models.delivery import Delivery
from worker.celery_app import celery


log = logging.getLogger(__name__)

POLL_SECONDS = 2
BATCH_SIZE = 100


async def _tick():
    log.info("tick: start")
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        log.info("tick: querying due deliveries...")
        stmt = (
            select(Delivery.id)
            .where(
                Delivery.dead_lettered_at.is_(None),
                Delivery.status.in_(["pending", "failed"]),
                (Delivery.next_retry_at.is_(None)) | (Delivery.next_retry_at <= func.now()),
            )
            .order_by(Delivery.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(BATCH_SIZE)
        )

        ids = (await db.execute(stmt)).scalars().all()
        log.info("tick: found %d deliveries", len(ids))

        if not ids:
            await db.commit()
            await engine.dispose()
            return 0

        # Mark as pending-publish (optional status) to prevent double enqueue
        await db.execute(
            update(Delivery)
            .where(Delivery.id.in_(ids))
            .values(status="publishing", last_attempt_at=func.now())
        )
        await db.commit()

    await engine.dispose()

    log.info("tick: enqueueing %d tasks to celery...", len(ids))
    for delivery_id in ids:
        celery.send_task("worker.tasks.publish_delivery", args=[delivery_id], queue="publish")
    log.info("tick: done enqueueing")

    return len(ids)


async def main():
    celery.connection().ensure_connection(max_retries=3)

    logging.basicConfig(level=logging.INFO)
    log.info("dispatcher: started")
    while True:
        try:
            await _tick()
        except Exception:
            log.exception("dispatcher: tick crashed")
        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
