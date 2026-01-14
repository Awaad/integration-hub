import asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.sql import func

from app.core.config import settings
from app.models.delivery import Delivery
from worker.celery_app import celery


POLL_SECONDS = 2
BATCH_SIZE = 100


async def _tick():
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
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

    for delivery_id in ids:
        celery.send_task("worker.tasks.publish_delivery", args=[delivery_id], queue="publish")

    return len(ids)

async def main():
    while True:
        await _tick()
        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
