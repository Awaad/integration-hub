from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from app.canonical.v1.listing import ListingCanonicalV1


@dataclass
class ProjectionWarning:
    code: str
    message: str


def project_listing_to_101evler_xml_ad(listing: ListingCanonicalV1) -> tuple[dict[str, Any], list[ProjectionWarning]]:
    """
    Returns a dict representing a single <ad> element fields (not the full XML).
    Phase 5 later will implement full mapping tables:
    - type_id, area_id, title_type_id, currency codes, room_count_id, etc.
    - and media mapping to <ad_pictures>.<ad_picture> items.

    For now we only return minimal fields needed to unblock registry/capabilities wiring.
    """
    warnings: list[ProjectionWarning] = []

    # 101evler requires stable unique <ad_key> and updates require <lastupdate> changes :contentReference[oaicite:8]{index=8}
    ad = {
        "ad_key": listing.canonical_id,
        "lastupdate": None,  # filled at feed generation time from Listing.updated_at
        "sale_or_rent": "R" if listing.purpose == "rent" else "S",
        "price": (listing.list_price.amount if listing.list_price else None),
        # TODO: currency mapping (101evler uses numeric IDs like 601/602 etc) :contentReference[oaicite:9]{index=9}
    }

    if ad["price"] is None:
        warnings.append(ProjectionWarning(code="MISSING_PRICE", message="101evler requires <price>; listing has no list_price."))

    return ad, warnings
