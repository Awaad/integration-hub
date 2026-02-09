from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from app.canonical.v1.listing import ListingCanonicalV1
from app.services.listing_state import canonical_status, is_active_status

@dataclass(frozen=True)
class ProjectionWarning:
    code: str
    message: str

@dataclass(frozen=True)
class ProjectedPayload:
    ok: bool
    payload: dict[str, Any] | None
    warnings: list[ProjectionWarning]
    errors: list[ProjectionWarning]

def project_mls_demo_push(
    *,
    canonical: ListingCanonicalV1,
    external_listing_id: str | None,
    # later derived from mapping tables)
    mapped: dict[str, Any] | None = None,
) -> ProjectedPayload:
    warnings: list[ProjectionWarning] = []
    errors: list[ProjectionWarning] = []

    status = canonical.status

    if not is_active_status(status):
        # destination policy may exclude inactive; projection still can return a "status" field
        warnings.append(ProjectionWarning(code="INACTIVE", message=f"Listing status={status}"))

    # Normalize media ordering + drop empty urls defensively
    media_items = list(canonical.media or [])
    media_items_sorted = sorted(
        [m for m in media_items if getattr(m, "url", None)],
        key=lambda m: (int(getattr(m, "order", 0) or 0), str(getattr(m, "url", ""))),
    )

    # avoid destination-specific naming for now
    p = {
        "schema": "mls_demo_push.listing",
        "schema_version": "1.0",
        "external_listing_id": external_listing_id,     # used for idempotent upserts
        "canonical_id": canonical.canonical_id,

        "status": status,
        "purpose": canonical.purpose,
        "title": canonical.title,
        "description": canonical.description,

        "price": {
            "amount": canonical.list_price.amount if canonical.list_price else None,
            "currency": canonical.list_price.currency if canonical.list_price else None,
        },

        "property": {
            "category": canonical.property.category if canonical.property else None,
            "subtype": canonical.property.subtype if canonical.property else None,
            "bedrooms": canonical.property.bedrooms if canonical.property else None,
            "bathrooms": canonical.property.bathrooms if canonical.property else None,
            "area_m2": canonical.property.area_m2 if canonical.property else None,
        },

        "location": {
            "country": canonical.address.country if canonical.address else None,  # 2-letter if known
            "city": canonical.address.city if canonical.address else None,
            "area": canonical.address.area if canonical.address else None,
            "lat": canonical.address.lat if canonical.address else None,
            "lng": canonical.address.lng if canonical.address else None,
        },

        "media": [
            {
                "url": str(m.url),
                "type": m.type,
                "order": int(m.order) if getattr(m, "order", None) is not None else None,
                "caption": getattr(m, "caption", None),
            }
            for m in media_items_sorted
        ],
    }

    # Basic validation 
    if not p["price"]["amount"] or not p["price"]["currency"]:
        warnings.append(ProjectionWarning(code="MISSING_PRICE", message="Missing price.amount or price.currency"))

    if not p["property"]["category"]:
        warnings.append(ProjectionWarning(code="MISSING_PROPERTY_CATEGORY", message="Missing property.category"))

    if not p["location"]["city"]:
        warnings.append(ProjectionWarning(code="MISSING_CITY", message="Missing location.city"))

    # true error example (should never happen because canonical_id required)
    if not p["canonical_id"]:
        errors.append(ProjectionWarning(code="MISSING_CANONICAL_ID", message="Missing canonical_id"))

    ok = len(errors) == 0
    return ProjectedPayload(ok=ok, payload=p if ok else None, warnings=warnings, errors=errors)
