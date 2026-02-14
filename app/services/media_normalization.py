from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import gen_id
from app.models.listing import Listing
from app.models.listing_media import ListingMedia
from app.models.media_object import MediaObject
from app.services.media_ingest import ingest_media_from_url
from app.services.retry import RetryPlan, mark_failure, mark_started, mark_success

from app.services.media_errors import MediaForbiddenError, MediaRetryableError
from app.services.media_circuit import record_failure


_MAX_MEDIA_ITEMS = 500
_PREFETCH_CHUNK = 200
_MAX_ERROR_SAMPLES = 10

LISTING_MEDIA_RETRY = RetryPlan(
    attempts_col="media_normalization_attempts",
    next_at_col="media_normalization_next_at",
    started_at_col="media_normalization_started_at",
    error_col="media_normalization_error",
)


def _normalize_media_item(item: dict[str, Any], idx: int) -> dict[str, Any]:
    url = str(item.get("url") or "").strip()
    if not url:
        return {"ok": False, "reason": "missing_url"}

    mtype = str(item.get("type") or "image").lower().strip()
    if mtype not in ("image", "video", "floorplan", "document"):
        mtype = "image"

    order = item.get("order")
    try:
        order_index = int(order) if order is not None else idx
    except Exception:
        order_index = idx

    caption = item.get("caption")
    caption = str(caption).strip() if caption else None

    return {
        "ok": True,
        "url": url,
        "type": mtype,
        "order_index": order_index,
        "caption": caption,
        "idx": idx,
    }


def _chunks(seq: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


async def _fetch_listing_media_link(
    db: AsyncSession,
    *,
    tenant_id: str,
    partner_id: str,
    agent_id: str,
    listing_id: str,
    media_id: str,
) -> ListingMedia | None:
    return (
        await db.execute(
            select(ListingMedia).where(
                ListingMedia.tenant_id == tenant_id,
                ListingMedia.partner_id == partner_id,
                ListingMedia.agent_id == agent_id,
                ListingMedia.listing_id == listing_id,
                ListingMedia.media_id == media_id,
            )
        )
    ).scalar_one_or_none()


def _build_error_summary(errors: list[str], *, created: int) -> str:
    if not errors:
        return f"media normalization failed (created={created})"
    return f"{'; '.join(errors[:_MAX_ERROR_SAMPLES])} (created={created})"


async def normalize_listing_media(
    db: AsyncSession,
    *,
    listing: Listing,
    actor_id: str = "media_normalizer",
) -> int:
    if not listing.agent_id:
        raise ValueError("listing.agent_id is required for media normalization")

    if listing.media_normalization_started_at is None:
        await mark_started(db, model=Listing, row_id=listing.id, plan=LISTING_MEDIA_RETRY, actor_id=actor_id)

    payload = listing.payload or {}
    media = payload.get("media") or []

    if not isinstance(media, list) or not media:
        await mark_success(
            db,
            model=Listing,
            row_id=listing.id,
            plan=LISTING_MEDIA_RETRY,
            actor_id=actor_id,
            normalized_at_col="media_normalized_at",
        )
        return 0

    if len(media) > _MAX_MEDIA_ITEMS:
        media = media[:_MAX_MEDIA_ITEMS]

    normalized: list[dict[str, Any]] = []
    for idx, raw in enumerate(media):
        if not isinstance(raw, dict):
            continue
        norm = _normalize_media_item(raw, idx)
        if norm.get("ok"):
            normalized.append(norm)

    if not normalized:
        await mark_success(
            db,
            model=Listing,
            row_id=listing.id,
            plan=LISTING_MEDIA_RETRY,
            actor_id=actor_id,
            normalized_at_col="media_normalized_at",
        )
        return 0

    existing_links = (
        await db.execute(
            select(ListingMedia).where(
                ListingMedia.tenant_id == listing.tenant_id,
                ListingMedia.partner_id == listing.partner_id,
                ListingMedia.agent_id == listing.agent_id,
                ListingMedia.listing_id == listing.id,
            )
        )
    ).scalars().all()

    existing_by_media_id = {lm.media_id: lm for lm in existing_links}
    has_primary = any(lm.is_primary for lm in existing_links)

    # prefetch MediaObjects by source_url (chunked)
    urls = sorted({n["url"] for n in normalized})
    mo_by_source_url: dict[str, MediaObject] = {}

    for url_chunk in _chunks(urls, _PREFETCH_CHUNK):
        mos = (
            await db.execute(
                select(MediaObject).where(
                    MediaObject.tenant_id == listing.tenant_id,
                    MediaObject.partner_id == listing.partner_id,
                    MediaObject.agent_id == listing.agent_id,
                    MediaObject.source_url.in_(url_chunk),
                )
            )
        ).scalars().all()
        for mo in mos:
            if mo.source_url:
                mo_by_source_url[mo.source_url] = mo

    created = 0
    had_errors = False
    errors: list[str] = []

    normalized_sorted = sorted(normalized, key=lambda n: (n["order_index"], n["idx"]))

    for norm in normalized_sorted:
        url = norm["url"]

        try:
            mo = mo_by_source_url.get(url)
            if mo is None:
                mo = await ingest_media_from_url(
                    db,
                    tenant_id=listing.tenant_id,
                    partner_id=listing.partner_id,
                    agent_id=listing.agent_id,
                    url=url,
                    actor_id=actor_id,
                )
                mo_by_source_url[url] = mo

        except MediaForbiddenError as e:
            had_errors = True
            if len(errors) < _MAX_ERROR_SAMPLES:
                errors.append(e.code.value)
            continue

        except MediaRetryableError as e:
            await record_failure(
                f"{listing.tenant_id}:{listing.partner_id}"
            )
            raise

        except Exception as e:
            had_errors = True
            if len(errors) < _MAX_ERROR_SAMPLES:
                errors.append("unexpected_error")
            continue

        existing = existing_by_media_id.get(mo.id)
        if existing:
            changed = False
            if existing.type != norm["type"]:
                existing.type = norm["type"]
                changed = True
            if existing.order_index != norm["order_index"]:
                existing.order_index = norm["order_index"]
                changed = True
            if existing.caption != norm["caption"]:
                existing.caption = norm["caption"]
                changed = True

            if (not has_primary) and (norm["type"] == "image") and (not existing.is_primary):
                try:
                    async with db.begin_nested():
                        existing.is_primary = True
                        await db.flush()
                    has_primary = True
                    changed = True
                except IntegrityError:
                    pass

            if changed:
                existing.updated_by = actor_id
            continue


        # attempt insert (possibly as primary)
        lm = ListingMedia(
            id=gen_id("lmd"),
            tenant_id=listing.tenant_id,
            partner_id=listing.partner_id,
            agent_id=listing.agent_id,
            listing_id=listing.id,
            media_id=mo.id,
            type=norm["type"],
            order_index=norm["order_index"],
            caption=norm["caption"],
            is_primary=(not has_primary) and (norm["type"] == "image"),
            created_by=actor_id,
            updated_by=actor_id,
        )

        try:
            async with db.begin_nested():
                db.add(lm)
                await db.flush()
            existing_by_media_id[mo.id] = lm
            if lm.is_primary:
                has_primary = True
            created += 1

        except IntegrityError:
            # Could be: link unique race OR primary unique race
            winner = await _fetch_listing_media_link(
                db,
                tenant_id=listing.tenant_id,
                partner_id=listing.partner_id,
                agent_id=listing.agent_id,
                listing_id=listing.id,
                media_id=mo.id,
            )

            if not winner and lm.is_primary:
                # Likely primary constraint blocked insert; retry with is_primary=False
                try:
                    lm2 = ListingMedia(
                        id=gen_id("lmd"),
                        tenant_id=listing.tenant_id,
                        partner_id=listing.partner_id,
                        agent_id=listing.agent_id,
                        listing_id=listing.id,
                        media_id=mo.id,
                        type=norm["type"],
                        order_index=norm["order_index"],
                        caption=norm["caption"],
                        is_primary=False,
                        created_by=actor_id,
                        updated_by=actor_id,
                    )
                    async with db.begin_nested():
                        db.add(lm2)
                        await db.flush()
                    existing_by_media_id[mo.id] = lm2
                    created += 1
                    continue
                except IntegrityError:
                    winner = await _fetch_listing_media_link(
                        db,
                        tenant_id=listing.tenant_id,
                        partner_id=listing.partner_id,
                        agent_id=listing.agent_id,
                        listing_id=listing.id,
                        media_id=mo.id,
                    )


            if not winner:
                had_errors = True
                if len(errors) < _MAX_ERROR_SAMPLES:
                    errors.append("IntegrityError: listing_media insert failed; winner not found")
                continue

            existing_by_media_id[mo.id] = winner

            # update winner best-effort
            changed = False
            if winner.type != norm["type"]:
                winner.type = norm["type"]
                changed = True
            if winner.order_index != norm["order_index"]:
                winner.order_index = norm["order_index"]
                changed = True
            if winner.caption != norm["caption"]:
                winner.caption = norm["caption"]
                changed = True

            if changed:
                winner.updated_by = actor_id
                try:
                    async with db.begin_nested():
                        await db.flush()
                except IntegrityError:
                    had_errors = True
                    if len(errors) < _MAX_ERROR_SAMPLES:
                        errors.append("IntegrityError: failed to update winner listing_media")

            if winner.is_primary:
                has_primary = True

    # Ensure pending updates are persisted (inserts were flushed; updates may not have been)
    try:
        await db.flush()
    except IntegrityError:
        had_errors = True
        if len(errors) < _MAX_ERROR_SAMPLES:
            errors.append("IntegrityError: flush failed after processing media")

    if had_errors:
        attempt_after = int(getattr(listing, "media_normalization_attempts", 0) or 0) + 1
        summary = _build_error_summary(errors, created=created)

        await mark_failure(
            db,
            model=Listing,
            row_id=listing.id,
            plan=LISTING_MEDIA_RETRY,
            actor_id=actor_id,
            error_message=summary,
            attempts_expr=Listing.media_normalization_attempts + 1,
            attempt_after=attempt_after,
        )
        return created

    await mark_success(
        db,
        model=Listing,
        row_id=listing.id,
        plan=LISTING_MEDIA_RETRY,
        actor_id=actor_id,
        normalized_at_col="media_normalized_at",
    )
    return created