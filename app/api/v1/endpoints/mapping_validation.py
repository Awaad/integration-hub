from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.listing import Listing
from app.models.partner_destination_setting import PartnerDestinationSetting
from app.services.auth import Actor, require_partner_admin
from app.canonical.v1.listing import ListingCanonicalV1
from app.services.destination_mapping import load_dest_enum_maps, resolve_enum_with_fallback


router = APIRouter()

def _slug(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "-")


@router.get("/partners/{partner_id}/destinations/{destination}/validate-mapping")
async def validate_destination_mapping(
    partner_id: str,
    destination: str,
    limit: int = Query(default=50, ge=1, le=500),
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
):
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    dest = destination.lower().strip()

    setting = (await db.execute(select(PartnerDestinationSetting).where(
        PartnerDestinationSetting.tenant_id == actor.tenant_id,
        PartnerDestinationSetting.partner_id == partner_id,
        PartnerDestinationSetting.destination == dest,
        PartnerDestinationSetting.is_enabled.is_(True),
    ))).scalar_one_or_none()

    if not setting:
        raise HTTPException(status_code=404, detail="Destination not enabled")
    

    cfg = setting.config or {}

     # Only implemented for 101evler for now
    if dest != "101evler":
        return {
            "destination": dest,
            "checked": 0,
            "ok": 0,
            "errors": [],
            "warnings": [],
            "hint": "Validation currently implemented for destination=101evler only.",
        }

    # Load DB enum maps once (DB preferred, config fallback allowed)
    enum_maps = await load_dest_enum_maps(
        db,
        destination="101evler",
        namespaces=["property_type", "currency", "rooms"],
    )
    db_type_map = enum_maps.get("property_type", {})
    db_currency_map = enum_maps.get("currency", {})
    db_rooms_map = enum_maps.get("rooms", {})

    cfg_type_map = cfg.get("type_id_map") or {}
    cfg_currency_map = cfg.get("currency_id_map") or {}
    cfg_rooms_map = cfg.get("room_count_id_map") or {}
    cfg_area_map = cfg.get("area_id_map") or {}

    rows = (await db.execute(select(Listing).where(
        Listing.tenant_id == actor.tenant_id,
        Listing.partner_id == partner_id,
        Listing.schema == "canonical.listing",
        Listing.schema_version == "1.0",
    ).limit(limit))).scalars().all()

    errors: list[dict] = []
    warnings: list[dict] = []
    ok = 0

    for r in rows:
        can = ListingCanonicalV1.model_validate(r.payload)
        
        listing_errors: list[dict] = []
        listing_warnings: list[dict] = []

        # Required for export
        if not can.list_price:
            listing_errors.append({"code": "MISSING_PRICE"})
            errors.append({"listing_id": r.id, "canonical_id": can.canonical_id, "errors": listing_errors})
            continue

        prop_type = getattr(can.property, "property_type", None) if can.property else None
        
        type_id, type_source = resolve_enum_with_fallback(
            source_key=prop_type,
            db_map=db_type_map,
            cfg_map=cfg_type_map,
        )
        if not type_id:
            listing_errors.append({"code": "MISSING_TYPE_ID", "detail": {"property_type": prop_type}})
        elif type_source == "config_fallback":
            listing_warnings.append({"code": "TYPE_ID_FALLBACK", "detail": {"property_type": prop_type}, "source": "config_fallback"})

        currency = can.list_price.currency
        currency_id, currency_source = resolve_enum_with_fallback(
            source_key=currency,
            db_map=db_currency_map,
            cfg_map=cfg_currency_map,
        )
        if not currency_id:
            listing_errors.append({"code": "MISSING_CURRENCY_ID", "detail": {"currency": currency}})
        elif currency_source == "config_fallback":
            listing_warnings.append({"code": "CURRENCY_ID_FALLBACK", "detail": {"currency": currency}, "source": "config_fallback"})

        # rooms is optional: missing should be warning (not error)
        rooms_val = None
        if can.property and getattr(can.property, "bedrooms", None) is not None:
            rooms_val = str(can.property.bedrooms)

        if rooms_val:
            room_id, room_source = resolve_enum_with_fallback(
                source_key=rooms_val,
                db_map=db_rooms_map,
                cfg_map=cfg_rooms_map,
            )
            if not room_id:
                listing_warnings.append({"code": "MISSING_ROOM_COUNT_ID", "detail": {"rooms": rooms_val}})
            elif room_source == "config_fallback":
                listing_warnings.append({"code": "ROOM_COUNT_ID_FALLBACK", "detail": {"rooms": rooms_val}, "source": "config_fallback"})

        # Area mapping (config for now, supports city:area then city)
        city_slug = _slug(can.address.city) if can.address and can.address.city else ""
        area_slug = _slug(getattr(can.address, "area", None) or "") if can.address else ""
        area_key = f"{city_slug}:{area_slug}" if area_slug else city_slug

        area_id = None
        if area_key:
            area_id = cfg_area_map.get(area_key) or cfg_area_map.get(city_slug)

        if not area_id:
            listing_errors.append({"code": "MISSING_AREA_ID", "detail": {"city": city_slug, "area": area_slug, "area_key": area_key}})

        if listing_errors:
            errors.append({"listing_id": r.id, "canonical_id": can.canonical_id, "errors": listing_errors})
        else:
            ok += 1

        if listing_warnings:
            warnings.append({"listing_id": r.id, "canonical_id": can.canonical_id, "warnings": listing_warnings})

    return {
        "destination": dest,
        "checked": len(rows),
        "ok": ok,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "hint": (
            "Errors block export. Warnings mean config fallback is being used because DB mappings are missing. "
            "Prefer populating DestinationEnumMapping to make mappings reusable across partners."
        ),
    }