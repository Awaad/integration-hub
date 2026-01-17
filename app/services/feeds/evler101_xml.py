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


def _iso(dt: datetime) -> str:
    # 101evler expects a “lastupdate” that changes for updates.
    # We use an ISO string; if their spec requires a different format, we’ll adjust later.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def build_101evler_xml(
    *,
    listings: Iterable[tuple[ListingCanonicalV1, datetime]],
    config: dict,
) -> tuple[bytes, list[FeedBuildWarning], int]:
    """
    listings: (canonical_listing, updated_at) pairs so we can set <lastupdate>.
    config mappings expected:
      - type_id_map: { "apartment": 1, "villa": 2, ... }
      - area_id_map: { "nicosia": 10, ... }  
      - currency_id_map: { "EUR": 601, "GBP": 602, ... }  (per destination)
    """
    warnings: list[FeedBuildWarning] = []
    root = Element("ads")

    type_map = config.get("type_id_map", {}) or {}
    area_map = config.get("area_id_map", {}) or {}
    currency_map = config.get("currency_id_map", {}) or {}

    count = 0

    for canonical, updated_at in listings:
        # Required-ish fields for any MLS: key, title, description, price, location, type
        property_type = getattr(canonical.property, "property_type", None) if canonical.property else None

        city_slug = (canonical.address.city or "").strip().lower() if canonical.address else ""
        area_slug = (getattr(canonical.address, "area", None) or "").strip().lower() if canonical.address else ""

        type_id = type_map.get(property_type)

        # preferred lookup: "city_slug:area_slug" (if area_slug present), else city_slug
        key = f"{city_slug}:{area_slug}" if area_slug else city_slug
        area_id = area_map.get(key) or area_map.get(city_slug)

        if not type_id:
            warnings.append(FeedBuildWarning(canonical.canonical_id, "MISSING_TYPE_ID", f"No type_id_map for property_type={property_type}"))
            continue
        if not area_id:
            warnings.append(FeedBuildWarning(canonical.canonical_id, "MISSING_AREA_ID", f"No area_id_map for key={key!r} (city={city_slug!r}, area={area_slug!r})"))
            continue
        if not canonical.list_price:
            warnings.append(FeedBuildWarning(canonical.canonical_id, "MISSING_PRICE", "Listing missing list_price"))
            continue

        currency = canonical.list_price.currency
        currency_id = currency_map.get(currency)
        if not currency_id:
            warnings.append(FeedBuildWarning(canonical.canonical_id, "MISSING_CURRENCY_ID", f"No currency_id_map for currency={currency}"))
            continue

        ad = SubElement(root, "ad")
        SubElement(ad, "ad_key").text = canonical.canonical_id
        SubElement(ad, "lastupdate").text = _iso(updated_at)

        # Minimal required info (we’ll expand later with the full spec)
        SubElement(ad, "type_id").text = str(type_id)
        SubElement(ad, "area_id").text = str(area_id)

        SubElement(ad, "ad_title").text = canonical.title
        SubElement(ad, "ad_description").text = canonical.description or ""

        SubElement(ad, "price").text = str(canonical.list_price.amount)
        SubElement(ad, "currency_id").text = str(currency_id)

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
