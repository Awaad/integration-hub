import asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.sql import func

from worker.celery_app import celery
from app.core.config import settings
import app.models  # noqa: F401  # ensures Models are registered
from app.models.outbox import OutboxEvent
from app.models.listing import Listing
from app.models.agent import Agent
from app.models.delivery import Delivery


async def _process_outbox_event(outbox_id: str, lease_id: str) -> None:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        ev = (await db.execute(select(OutboxEvent).where(OutboxEvent.id == outbox_id))).scalar_one_or_none()
        if not ev:
            await engine.dispose()
            return

        # Lease ownership check
        if ev.lease_id != lease_id or ev.status != "processing":
            # Another dispatcher reclaimed it or it's already done.
            await engine.dispose()
            return

        try:
            if ev.event_type == "listing.upserted":
                listing_id = ev.payload["listing_id"]
                listing = (await db.execute(select(Listing).where(Listing.id == listing_id))).scalar_one()

                agent = (await db.execute(select(Agent).where(Agent.id == listing.agent_id))).scalar_one()
                allowed = agent.rules.get("allowed_destinations", [])

                for destination in allowed:
                    d = (await db.execute(
                        select(Delivery).where(
                            Delivery.tenant_id == listing.tenant_id,
                            Delivery.destination == destination,
                            Delivery.listing_id == listing.id,
                        )
                    )).scalar_one_or_none()

                    if not d:
                        d = Delivery(
                            tenant_id=listing.tenant_id,
                            partner_id=listing.partner_id,
                            agent_id=listing.agent_id,
                            listing_id=listing.id,
                            destination=destination,
                            status="pending",
                            attempts=0,
                        )
                        db.add(d)
                    else:
                        # If listing changed again, re-queue if it was failed/pending/publishing
                        # If already success, we still want to republish when content changes.
                        # We keep it simple: set to pending unless dead_lettered.
                        if d.dead_lettered_at is None:
                            d.status = "pending"
                            d.last_error = None
                            d.status_detail = None
                            # if we have next_retry_at clear it here
                            if hasattr(d, "next_retry_at"):
                                d.next_retry_at = None

                    # store "last_synced_hash" in ListingExternalMapping later 
                    # so publishing can skip if no change.


                        # Mark done only if lease still matches
                        result = await db.execute(
                            update(OutboxEvent)
                            .where(OutboxEvent.id == outbox_id, OutboxEvent.lease_id == lease_id)
                            .values(
                                status="done",
                                processed_at=func.now(),
                                lease_id=None,
                                lease_expires_at=None,
                            )
                        )


            if result.rowcount == 0:
                # lease lost; do not overwrite
                await db.rollback()
                await engine.dispose()
                return

            await db.commit()

        except Exception as e:
            # Return to pending if lease matches; store error
            await db.execute(
                update(OutboxEvent)
                .where(OutboxEvent.id == outbox_id, OutboxEvent.lease_id == lease_id)
                .values(
                    status="pending",
                    lease_id=None,
                    lease_expires_at=None,
                    processing_started_at=None,
                    last_error=f"{type(e).__name__}: {e}",
                )
            )
            await db.commit()

    await engine.dispose()


@celery.task(name="worker.tasks.process_outbox_event", bind=True, max_retries=5)
def process_outbox_event(self, outbox_id: str, lease_id: str) -> None:
    asyncio.run(_process_outbox_event(outbox_id, lease_id))
