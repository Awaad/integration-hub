from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.listing import Listing
from app.models.partner_destination_setting import PartnerDestinationSetting
from app.services.auth import Actor, require_partner_admin
from app.canonical.v1.listing import ListingCanonicalV1

router = APIRouter()

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

    rows = (await db.execute(select(Listing).where(
        Listing.tenant_id == actor.tenant_id,
        Listing.partner_id == partner_id,
        Listing.schema == "canonical.listing",
        Listing.schema_version == "1.0",
    ).limit(limit))).scalars().all()

    issues = []
    ok = 0

    for r in rows:
        can = ListingCanonicalV1.model_validate(r.payload)
        # minimal checks for 101evler (we’ll expand later):
        # - type_id mapping exists
        # - area mapping exists
        # - currency mapping exists
        # - price exists
        prop_type = getattr(can.property, "property_type", None) if can.property else None
        type_map = (cfg.get("type_id_map") or {})
        currency_map = (cfg.get("currency_id_map") or {})
        area_map = (cfg.get("area_id_map") or {})

        city = (can.address.city or "").strip().lower() if can.address else ""
        area = (getattr(can.address, "area", None) or "").strip().lower() if can.address else ""
        area_key = f"{city}:{area}" if area else city

        missing = []
        if dest == "101evler":
            if not type_map.get(prop_type):
                missing.append({"code": "MISSING_TYPE_ID", "detail": {"property_type": prop_type}})
            if not can.list_price:
                missing.append({"code": "MISSING_PRICE"})
            else:
                if not currency_map.get(can.list_price.currency):
                    missing.append({"code": "MISSING_CURRENCY_ID", "detail": {"currency": can.list_price.currency}})
            if not area_map.get(area_key) and not area_map.get(city):
                missing.append({"code": "MISSING_AREA_ID", "detail": {"city": city, "area": area}})

        if missing:
            issues.append({"listing_id": r.id, "missing": missing})
        else:
            ok += 1

    return {
        "destination": dest,
        "checked": len(rows),
        "ok": ok,
        "issues": issues,
        "hint": "Populate config maps (type_id_map, currency_id_map, area_id_map) or load shared geo mappings for reuse.",
    }
