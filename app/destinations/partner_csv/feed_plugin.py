from __future__ import annotations
import csv
import hashlib
from io import StringIO
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.destinations.feeds.base import FeedBuildOutput
from app.canonical.v1.listing import ListingCanonicalV1
from app.models.listing import Listing

class PartnerCSVFeedPlugin:
    destination = "partner_csv"

    async def build(self, *, db: AsyncSession, tenant_id: str, partner_id: str, config: dict[str, Any]) -> FeedBuildOutput:
        rows = (await db.execute(select(Listing).where(
            Listing.tenant_id == tenant_id,
            Listing.partner_id == partner_id,
            Listing.schema == "canonical.listing",
            Listing.schema_version == "1.0",
        ))).scalars().all()

        buf = StringIO()
        w = csv.writer(buf)
        w.writerow(["listing_id", "title", "price_amount", "currency", "city"])

        count = 0
        for r in rows:
            can = ListingCanonicalV1.model_validate(r.payload)
            price = can.list_price.amount if can.list_price else ""
            cur = can.list_price.currency if can.list_price else ""
            city = can.address.city if can.address else ""
            w.writerow([can.canonical_id, can.title or "", price, cur, city])
            count += 1

        data = buf.getvalue().encode("utf-8")
        h = hashlib.sha256(data).hexdigest()

        return FeedBuildOutput(
            format="csv",
            bytes=data,
            listing_count=count,
            content_hash=h,
            meta={"generator": "partner_csv_v1"},
        )
