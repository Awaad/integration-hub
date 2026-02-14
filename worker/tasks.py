from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.sql import func

from worker.celery_app import celery
from app.core.config import settings
import app.models  # noqa: F401

from app.models.outbox import OutboxEvent
from app.models.listing import Listing
from app.models.agent import Agent
from app.models.delivery import Delivery

from app.services.destinations import get_enabled_destinations_for_partner
from app.services.outbox_service import enqueue_outbox_event
from app.services.media_normalization import normalize_listing_media
from app.services.retry import compute_backoff_seconds

log = logging.getLogger(__name__)

# module-level engine/sessionmaker (IMPORTANT for performance)
_engine = create_async_engine(settings.database_url, pool_pre_ping=True)
_Session = async_sessionmaker(_engine, expire_on_commit=False)

MAX_ATTEMPTS_DEFAULT = 25


def _dedupe_key_listing_media_normalize(listing_id: str, content_hash: str) -> str:
    return f"listing.media.normalize:{listing_id}:{content_hash}"


async def _mark_outbox_done(db, *, outbox_id: str, lease_id: str) -> bool:
    result = await db.execute(
        update(OutboxEvent)
        .where(OutboxEvent.id == outbox_id, OutboxEvent.lease_id == lease_id)
        .values(
            status="done",
            processed_at=datetime.now(timezone.utc),
            lease_id=None,
            lease_expires_at=None,
            next_retry_at=None,
            last_error=None,
        )
    )
    return result.rowcount == 1


async def _dead_letter_or_retry_outbox(
    db,
    *,
    outbox_id: str,
    lease_id: str,
    attempts: int,
    error: str,
    max_attempts: int = MAX_ATTEMPTS_DEFAULT,
    base: int = 10,
    cap: int = 900,
) -> None:
    """
    Return to pending with backoff, or dead-letter if attempts exceeded.
    Assumes we're still the lease owner.
    """
    if attempts >= max_attempts:
        await db.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == outbox_id, OutboxEvent.lease_id == lease_id)
            .values(
                status="dead",
                dead_lettered_at=func.now(),
                processed_at=func.now(),
                lease_id=None,
                lease_expires_at=None,
                processing_started_at=None,
                last_error=error,
            )
        )
        return

    delay = compute_backoff_seconds(attempts, base=base, cap=cap)
    await db.execute(
        update(OutboxEvent)
        .where(OutboxEvent.id == outbox_id, OutboxEvent.lease_id == lease_id)
        .values(
            status="pending",
            lease_id=None,
            lease_expires_at=None,
            processing_started_at=None,
            last_error=error,
            next_retry_at=datetime.now(timezone.utc) + timedelta(seconds=delay),
        )
    )


async def _handle_listing_upserted(db, *, ev: OutboxEvent) -> None:
    listing_id = ev.payload["listing_id"]
    listing = (await db.execute(select(Listing).where(Listing.id == listing_id))).scalar_one()

    enabled = await get_enabled_destinations_for_partner(
        db,
        tenant_id=listing.tenant_id,
        partner_id=listing.partner_id,
    )

    agent = (await db.execute(select(Agent).where(Agent.id == listing.agent_id))).scalar_one()
    allowed = set((agent.rules or {}).get("allowed_destinations", []))
    targets = sorted(allowed & set(enabled))

    # upsert deliveries
    for destination in targets:
        d = (
            await db.execute(
                select(Delivery).where(
                    Delivery.tenant_id == listing.tenant_id,
                    Delivery.destination == destination,
                    Delivery.listing_id == listing.id,
                )
            )
        ).scalar_one_or_none()

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
            if d.dead_lettered_at is None:
                d.status = "pending"
                d.last_error = None
                d.status_detail = None
                if hasattr(d, "next_retry_at"):
                    d.next_retry_at = None

    # enqueue media normalization if listing has media and not normalized for this hash
    media = (listing.payload or {}).get("media") or []
    has_media_urls = isinstance(media, list) and any(
        isinstance(it, dict) and str(it.get("url") or "").strip() for it in media
    )

    if has_media_urls and (getattr(listing, "media_normalized_hash", None) != listing.content_hash):
        dedupe_key = _dedupe_key_listing_media_normalize(listing.id, listing.content_hash)
        await enqueue_outbox_event(
            db,
            aggregate_type="listing",
            aggregate_id=listing.id,
            event_type="listing.media.normalize",
            payload={
                "listing_id": listing.id,
                "content_hash": listing.content_hash,
            },
            dedupe_key=dedupe_key,
            actor_id="outbox",
        )


async def _handle_listing_media_normalize(db, *, ev: OutboxEvent) -> None:
    listing_id = ev.payload["listing_id"]
    target_hash = ev.payload.get("content_hash")

    listing = (await db.execute(select(Listing).where(Listing.id == listing_id))).scalar_one()

    # If listing changed since event was created, skip (stale event)
    if target_hash and listing.content_hash != target_hash:
        return

    # If already normalized for this version, nothing to do
    if getattr(listing, "media_normalized_hash", None) == listing.content_hash:
        return

    # Run normalization (this will use ingest policy + typed errors once we wire them)
    created = await normalize_listing_media(db, listing=listing, actor_id="media_normalizer")

    # On success, record hash so we don't redo for same content_hash
    if created is not None:
        await db.execute(
            update(Listing)
            .where(Listing.id == listing_id)
            .values(
                media_normalized_hash=listing.content_hash,
                updated_by="media_normalizer",
            )
        )

    log.info("listing.media.normalize listing=%s created_links=%d", listing.id, created)


async def _process_outbox_event(outbox_id: str, lease_id: str) -> None:
    async with _Session() as db:
        ev = (await db.execute(select(OutboxEvent).where(OutboxEvent.id == outbox_id))).scalar_one_or_none()
        if not ev:
            return

        # Lease ownership check
        if ev.lease_id != lease_id or ev.status != "processing":
            return

        try:
            if ev.event_type == "listing.upserted":
                await _handle_listing_upserted(db, ev=ev)
            elif ev.event_type == "listing.media.normalize":
                await _handle_listing_media_normalize(db, ev=ev)
            else:
                # Unknown event types should be marked done to avoid blocking
                log.warning("unknown outbox event_type=%s id=%s", ev.event_type, ev.id)

            # Mark done only if lease still matches
            ok = await _mark_outbox_done(db, outbox_id=outbox_id, lease_id=lease_id)
            if not ok:
                await db.rollback()
                return

            await db.commit()

        except Exception as e:
            # Return to pending or dead-letter if lease matches
            err = f"{type(e).__name__}: {e}"
            try:
                await _dead_letter_or_retry_outbox(
                    db,
                    outbox_id=outbox_id,
                    lease_id=lease_id,
                    attempts=int(ev.attempts or 0),
                    error=err,
                )
                await db.commit()
            except Exception:
                await db.rollback()
                log.exception("failed updating outbox failure state id=%s", outbox_id)

            log.exception("outbox event failed id=%s type=%s", outbox_id, ev.event_type)


@celery.task(name="worker.tasks.process_outbox_event", bind=True, max_retries=0)
def process_outbox_event(self, outbox_id: str, lease_id: str) -> None:
    # max_retries=0 because we manage retries in DB (next_retry_at)
    asyncio.run(_process_outbox_event(outbox_id, lease_id))