from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
import app.models  # noqa: F401
from app.services.outbox_dispatcher import OutboxDispatchConfig, dispatch_outbox

log = logging.getLogger(__name__)

POLL_SECONDS = 2


async def _tick(Session) -> int:
    async with Session() as db:
        n = await dispatch_outbox(db, cfg=OutboxDispatchConfig(batch_size=200, lease_seconds=60, queue="outbox"))
        await db.commit()
        return n


async def main():
    logging.basicConfig(level=logging.INFO)
    log.info("outbox_runner: started")

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        while True:
            try:
                n = await _tick(Session)
                if n:
                    log.info("outbox_runner: dispatched %d events", n)
            except Exception:
                log.exception("outbox_runner: tick crashed")
            await asyncio.sleep(POLL_SECONDS)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())