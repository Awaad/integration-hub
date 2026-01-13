import asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.sql import func

from worker.celery_app import celery
from app.core.config import settings
from app.models.outbox import OutboxEvent
from app.models.listing import Listing
from app.models.agent import Agent
from app.models.delivery import Delivery, DeliveryAttempt


async def _process_outbox_event(outbox_id: str) -> None:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        ev = (await db.execute(select(OutboxEvent).where(OutboxEvent.id == outbox_id))).scalar_one_or_none()
        if not ev:
            return

        if ev.status not in ("processing", "sent", "pending"):
            return

        if ev.event_type == "listing.upserted":
            listing_id = ev.payload["listing_id"]
            listing = (await db.execute(select(Listing).where(Listing.id == listing_id))).scalar_one()

            agent = (await db.execute(select(Agent).where(Agent.id == listing.agent_id))).scalar_one()
            allowed = agent.rules.get("allowed_destinations", [])

            for destination in allowed:
                # Upsert delivery row (unique per tenant+destination+listing)
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
                    )
                    db.add(d)
                    await db.flush()

                # Record an attempt as "success" for now (mock publish)
                attempt = DeliveryAttempt(
                    delivery_id=d.id,
                    status="success",
                    request={"content_hash": listing.content_hash, "schema": listing.schema},
                    response={"mock": True},
                )
                db.add(attempt)

                d.status = "success"
                d.last_attempt_at = func.now()
                d.last_success_at = func.now()

            ev.status = "done"
            ev.processed_at = func.now()

        elif ev.event_type == "listing.deleted":
            ev.status = "done"
            ev.processed_at = func.now()

        else:
            ev.status = "done"
            ev.processed_at = func.now()

        await db.commit()

    await engine.dispose()


@celery.task(name="worker.tasks.process_outbox_event", bind=True, max_retries=5)
def process_outbox_event(self, outbox_id: str) -> None:
    asyncio.run(_process_outbox_event(outbox_id))
