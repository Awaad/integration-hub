import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from worker.celery_app import celery
from app.core.config import settings
from worker.publish import publish_delivery


async def _publish_delivery(delivery_id: str) -> None:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        await publish_delivery(db, delivery_id)
        await db.commit()

    await engine.dispose()


@celery.task(name="worker.tasks.publish_delivery", bind=True, max_retries=5)
def publish_delivery_task(self, delivery_id: str) -> None:
    asyncio.run(_publish_delivery(delivery_id))
