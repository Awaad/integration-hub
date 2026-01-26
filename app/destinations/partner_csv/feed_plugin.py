from __future__ import annotations
import csv
import hashlib
from io import StringIO
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.destinations.feeds.base import FeedBuildOutput
from app.destinations.registry import get_destination_connector
from app.canonical.v1.listing import ListingCanonicalV1
from app.models.listing import Listing
from app.services.listing_state import canonical_status, should_include_listing
from app.services.feed_stats import summarize_skips


class PartnerCSVFeedPlugin:
    destination = "partner_csv"
    format = "csv"

    async def build(self, *, db: AsyncSession, tenant_id: str, partner_id: str, config: dict[str, Any]) -> FeedBuildOutput:

        connector = get_destination_connector(self.destination)
        policy = connector.capabilities().listing_inclusion_policy

        rows = (await db.execute(select(Listing).where(
            Listing.tenant_id == tenant_id,
            Listing.partner_id == partner_id,
            Listing.schema == "canonical.listing",
            Listing.schema_version == "1.0",
        ))).scalars().all()

        skipped: list[dict[str, Any]] = []

        buf = StringIO()
        w = csv.writer(buf)
        w.writerow(["listing_id", "title", "price_amount", "currency", "city"])

        # Header depends on policy
        header = ["listing_id", "title", "price_amount", "currency", "city"]
        if policy == "include_with_status":
            header.append("status")
        w.writerow(header)

        count = 0
        for r in rows:
            status = canonical_status(r.payload)

            # Exclude inactive if policy says so
            if not should_include_listing(policy=policy, status=status):
                skipped.append({"listing_id": str(r.id), "reason": "policy_excluded", "detail": f"status={status}"})
                continue

            can = ListingCanonicalV1.model_validate(r.payload)
            price = can.list_price.amount if can.list_price else ""
            cur = can.list_price.currency if can.list_price else ""
            city = can.address.city if can.address else ""

            out_row = [can.canonical_id, can.title or "", price, cur, city]
            if policy == "include_with_status":
                out_row.append(status)

            w.writerow([can.canonical_id, can.title or "", price, cur, city])
            count += 1

        data = buf.getvalue().encode("utf-8")
        h = hashlib.sha256(data).hexdigest()

        skipped_by_reason = summarize_skips(skipped)

        meta: dict[str, Any] = {
            "generator": "partner_csv_v1",
            "listing_inclusion_policy": policy,
            "skipped_count": int(sum(skipped_by_reason.values())),
            "skipped_by_reason": dict(skipped_by_reason),
        }
        meta["skipped"] = skipped[:200]

        return FeedBuildOutput(
            format="csv",
            bytes=data,
            listing_count=count,
            content_hash=h,
            meta=meta,
        )
