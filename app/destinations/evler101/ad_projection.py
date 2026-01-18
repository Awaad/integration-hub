from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.canonical.v1.listing import ListingCanonicalV1


@dataclass
class Evler101ProjectionWarning:
    code: str
    message: str


def format_lastupdate(dt: datetime) -> str:
    """
    101evler sample uses: '2023-10-20 20:21:00' (no offset). :contentReference[oaicite:6]{index=6}
    We emit UTC time in that format.
    """
    if dt.tzinfo:
        dt = dt.astimezone(tz=None).replace(tzinfo=None)  # drop tz; already normalized upstream if desired
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def sale_or_rent(purpose: str | None) -> str | None:
    # Spec: S=For Sale, R=To Rent :contentReference[oaicite:7]{index=7}
    if not purpose:
        return None
    p = purpose.lower().strip()
    if p in ("rent", "rental", "to_rent"):
        return "R"
    return "S"


def project_ad_fields(
    *,
    listing: ListingCanonicalV1,
    updated_at: datetime,
    type_id: str,
    area_id: str,
    currency_id: str,
    first_realtor_id: str | None,
    room_count_id: str | None,
    title_type_id: str | None,
) -> tuple[dict[str, Any], list[Evler101ProjectionWarning]]:
    """
    Returns a dict of tags -> values for a single <ad>.
    We keep this module focused on shaping tags, not DB lookups.
    """
    w: list[Evler101ProjectionWarning] = []

    # Titles: PDF shows language-specific tags like ad_title_en, ad_description_en :contentReference[oaicite:8]{index=8}
    title = listing.title or ""
    desc = listing.description or ""

    # Price: <price> + <price_for> and <currency> (numeric) :contentReference[oaicite:9]{index=9}
    price = listing.list_price.amount if listing.list_price else None
    if price is None:
        w.append(Evler101ProjectionWarning("MISSING_PRICE", "101evler requires <price>."))

    s_or_r = sale_or_rent(getattr(listing, "purpose", None))
    if not s_or_r:
        w.append(Evler101ProjectionWarning("MISSING_PURPOSE", "Cannot determine <sale_or_rent> (S/R)."))

    # Reference: use source_listing_id if present
    ref = getattr(listing, "source_listing_id", None) or listing.canonical_id

    # scalar fields from canonical if present
    bedrooms = getattr(getattr(listing, "property", None), "bedrooms", None)
    bathrooms = getattr(getattr(listing, "property", None), "bathrooms", None)

    total_area = getattr(getattr(listing, "property", None), "area", None)  # depends on canonical
    lat = getattr(getattr(listing, "address", None), "lat", None)
    lng = getattr(getattr(listing, "address", None), "lng", None)

    ad: dict[str, Any] = {
        "ad_key": listing.canonical_id,               # unique + stable :contentReference[oaicite:10]{index=10}
        "lastupdate": format_lastupdate(updated_at),  # must change on updates :contentReference[oaicite:11]{index=11}
        "type_id": str(type_id),
        "area_id": str(area_id),
        "reference_no": str(ref),
        "sale_or_rent": s_or_r,
        "ad_title_en": title,
        "ad_description_en": desc,
        "price": str(price) if price is not None else None,
        "price_for": "T",              # Total price (default) :contentReference[oaicite:12]{index=12}
        "currency": str(currency_id),  # spec uses <currency> numeric (e.g. 601) :contentReference[oaicite:13]{index=13}
    }

    # Realtor IDs shown in sample feed :contentReference[oaicite:14]{index=14}
    if first_realtor_id:
        ad["first_realtor_id"] = str(first_realtor_id)
    else:
        # Not necessarily required for everyone, but we warn (common MLS requirement)
        w.append(Evler101ProjectionWarning("MISSING_REALTOR_ID", "No first_realtor_id (agent external id) provided."))

    # Title type optional mapping table exists :contentReference[oaicite:15]{index=15}
    if title_type_id:
        ad["title_type_id"] = str(title_type_id)

    # Rooms enum table exists :contentReference[oaicite:16]{index=16}
    if room_count_id:
        ad["room_count_id"] = str(room_count_id)

    if bedrooms is not None:
        ad["bedroom_count"] = str(bedrooms)
    if bathrooms is not None:
        ad["bathroom_count"] = str(bathrooms)

    if total_area is not None:
        ad["total_area"] = str(total_area)
    if lat is not None:
        ad["lat"] = str(lat)
    if lng is not None:
        ad["lng"] = str(lng)

    return ad, w
