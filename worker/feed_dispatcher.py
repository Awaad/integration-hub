import asyncio
import logging
from app.destinations.connector_registry import get_destination_connector
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
from app.models.partner_destination_setting import PartnerDestinationSetting
from app.services.hosted_feed import build_partner_feed_snapshot
from app.services.storage import LocalObjectStore
from app.services.partner_destination_config import ensure_feed_token


log = logging.getLogger(__name__)

POLL_SECONDS = 30

async def _tick():
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    store = LocalObjectStore(settings.feed_storage_dir)

    async with Session() as db:
        rows = (await db.execute(
            select(PartnerDestinationSetting).where(
                PartnerDestinationSetting.is_enabled.is_(True),
            )
        )).scalars().all()

        built = 0
        for s in rows:
            # only handle hosted_feed destinations (we’ll check via registry later)
            try:
                connector = get_destination_connector(s.destination)
            except KeyError:
                log.warning("feed_dispatcher: unknown destination=%s (skipping)", s.destination)
                continue

            caps = connector.capabilities()
            if caps.transport != "hosted_feed":
                continue

            # Ensure destination has a feed_token before generating snapshot
            await ensure_feed_token(
                db,
                tenant_id=s.tenant_id,
                partner_id=s.partner_id,
                destination=s.destination,
            )

            await build_partner_feed_snapshot(
                db,
                tenant_id=s.tenant_id,
                partner_id=s.partner_id,
                destination=s.destination,
                store=store,
            )
            built += 1

        await db.commit()

    await engine.dispose()
    return built

async def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            n = await _tick()
            log.info("feed_dispatcher: built %d snapshots", n)
        except Exception:
            log.exception("feed_dispatcher: tick crashed")
        await asyncio.sleep(POLL_SECONDS)

if __name__ == "__main__":
    asyncio.run(main())
