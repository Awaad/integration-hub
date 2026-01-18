from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from xml.etree.ElementTree import Element, SubElement, tostring

from app.canonical.v1.listing import ListingCanonicalV1


@dataclass
class FeedBuildWarning:
    listing_id: str
    code: str
    message: str


@dataclass(frozen=True)
class Evler101FeedItem:
    canonical: ListingCanonicalV1
    updated_at: datetime
    type_id: str
    area_id: str
    currency_id: str
    room_count_id: str | None = None


def _iso(dt: datetime) -> str:
    # 101evler expects a “lastupdate” that changes for updates.
    # We use an ISO string; if their spec requires a different format, we’ll adjust later.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def build_101evler_xml(
    *,
    items: Iterable[Evler101FeedItem],
) -> tuple[bytes, list[FeedBuildWarning], int]:
    """
    items: Evler101FeedItem objects.
    config mappings expected:
      - type_id_map: { "apartment": 1, "villa": 2, ... }
      - area_id_map: { "nicosia": 10, ... }  
      - currency_id_map: { "EUR": 601, "GBP": 602, ... }  (per destination)
    """
    warnings: list[FeedBuildWarning] = []
    root = Element("ads")

    count = 0

    for item in items:
        canonical = item.canonical

        if not canonical.list_price:
            # Should be filtered before, but keep guard.
            warnings.append(FeedBuildWarning(canonical.canonical_id, "MISSING_PRICE", "Listing missing list_price"))
            continue

        ad = SubElement(root, "ad")
        SubElement(ad, "ad_key").text = canonical.canonical_id
        SubElement(ad, "lastupdate").text = _iso(item.updated_at)

        # Minimal required info (we’ll expand later with the full spec)
        SubElement(ad, "type_id").text = str(item.type_id)
        SubElement(ad, "area_id").text = str(item.area_id)

        SubElement(ad, "ad_title").text = canonical.title
        SubElement(ad, "ad_description").text = canonical.description or ""

        SubElement(ad, "price").text = str(canonical.list_price.amount)
        SubElement(ad, "currency_id").text = str(item.currency_id)

        # media: 101evler dedupes photos by URL; keep stable ordering :contentReference[oaicite:2]{index=2}
        pics = SubElement(ad, "ad_pictures")
        images = [m for m in (canonical.media or []) if m.type == "image"]
        images_sorted = sorted(images, key=lambda m: (m.order, m.id))
        for i, m in enumerate(images_sorted, start=1):
            pic = SubElement(pics, "ad_picture")
            SubElement(pic, "picture_url").text = str(m.url)
            SubElement(pic, "order_by").text = str(i)

        count += 1

    xml_bytes = tostring(root, encoding="utf-8", xml_declaration=True)
    return xml_bytes, warnings, count
