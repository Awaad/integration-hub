from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.sql import func

from app.core.config import settings
import app.models  # noqa: F401
from app.models.listing import Listing
from app.services.media_normalization import normalize_listing_media
from app.services.retry import RetryPlan, mark_failure

log = logging.getLogger(__name__)

POLL_SECONDS = 5
BATCH_SIZE = 20
CONCURRENCY = 5

# if a worker crashes mid-listing, allow reclaim after this
STARTED_STALE_AFTER = timedelta(minutes=15)

LISTING_MEDIA_RETRY = RetryPlan(
    attempts_col="media_normalization_attempts",
    next_at_col="media_normalization_next_at",
    started_at_col="media_normalization_started_at",
    error_col="media_normalization_error",
)


async def _claim_batch(db) -> list[str]:
    """
    Claim a batch of due listings using row locks (SKIP LOCKED).
    We DO NOT increment attempts here. Attempts are incremented only on failure.
    """
    now = func.now()

    # allow reclaim if started_at is stale
    stale_cutoff = now - STARTED_STALE_AFTER

    stmt = (
        select(Listing.id)
        .where(
            Listing.media_normalized_at.is_(None),
            or_(Listing.media_normalization_next_at.is_(None), Listing.media_normalization_next_at <= now),
            or_(Listing.media_normalization_started_at.is_(None), Listing.media_normalization_started_at <= stale_cutoff),
        )
        .order_by(
            Listing.media_normalization_next_at.asc().nullsfirst(),
            Listing.created_at.asc(),
        )
        .with_for_update(skip_locked=True)
        .limit(BATCH_SIZE)
    )

    ids = [rid for (rid,) in (await db.execute(stmt)).all()]
    if not ids:
        return []

    # mark claimed
    await db.execute(
        update(Listing)
        .where(Listing.id.in_(ids))
        .values(
            media_normalization_started_at=now,
            media_normalization_error=None,
            updated_by="media_normalizer",
        )
    )
    return ids


async def _process_one(Session, listing_id: str) -> None:
    async with Session() as db:
        listing = (await db.execute(select(Listing).where(Listing.id == listing_id))).scalar_one()

        try:
            created = await normalize_listing_media(db, listing=listing, actor_id="media_normalizer")
            # normalize_listing_media handles success/failure bookkeeping itself.
            await db.commit()
            log.info("normalized listing=%s created_links=%d", listing_id, created)

        except Exception as e:
            # session may be in failed state; rollback before retry bookkeeping
            try:
                await db.rollback()
            except Exception:
                pass

            # Unexpected crash path: schedule retry via shared retry helper
            attempt_after = int(getattr(listing, "media_normalization_attempts", 0) or 0) + 1
            msg = f"{type(e).__name__}: {e}"

            try:
                await mark_failure(
                    db,
                    model=Listing,
                    row_id=listing_id,
                    plan=LISTING_MEDIA_RETRY,
                    actor_id="media_normalizer",
                    error_message=msg,
                    attempts_expr=Listing.media_normalization_attempts + 1,
                    attempt_after=attempt_after,
                )
                await db.commit()
            except Exception:
                try:
                    await db.rollback()
                except Exception:
                    pass
                log.exception("failed to mark_failure listing=%s", listing_id)

            log.exception("normalize crashed listing=%s", listing_id)


async def _tick(Session) -> int:
    async with Session() as db:
        ids = await _claim_batch(db)
        await db.commit()

    if not ids:
        return 0

    sem = asyncio.Semaphore(CONCURRENCY)

    async def run_one(lid: str):
        async with sem:
            await _process_one(Session, lid)

    results = await asyncio.gather(*(run_one(lid) for lid in ids), return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            log.exception("media_normalizer task failed", exc_info=r)

    return len(ids)


async def main():
    logging.basicConfig(level=logging.INFO)
    log.info("media_normalizer: started")

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        while True:
            try:
                await _tick(Session)
            except Exception:
                log.exception("media_normalizer: tick crashed")
            await asyncio.sleep(POLL_SECONDS)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())