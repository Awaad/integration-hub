from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.listing import Listing
from app.models.partner_destination_setting import PartnerDestinationSetting
from app.services.auth import Actor, require_partner_admin
from app.canonical.v1.listing import ListingCanonicalV1

from app.services.destination_mapping import resolve_dest_enum
from app.models.geo_country import GeoCountry
from app.models.geo_city import GeoCity
from app.models.geo_area import GeoArea
from app.models.destination_geo_mapping import DestinationGeoMapping

router = APIRouter()

def _slug(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "-")

@router.get("/partners/{partner_id}/destinations/{destination}/mapping-diff")
async def mapping_diff(
    partner_id: str,
    destination: str,
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

    rows = (await db.execute(select(Listing).where(
        Listing.tenant_id == actor.tenant_id,
        Listing.partner_id == partner_id,
        Listing.schema == "canonical.listing",
        Listing.schema_version == "1.0",
    ))).scalars().all()

    missing_property_types: set[str] = set()
    missing_currencies: set[str] = set()
    missing_geo: set[str] = set()

    exportable = 0

    # Preload NCY country if needed
    country = None
    if dest == "101evler":
        country = (await db.execute(select(GeoCountry).where(GeoCountry.code == "NCY"))).scalar_one_or_none()

    for r in rows:
        can = ListingCanonicalV1.model_validate(r.payload)

        ok = True

        if dest == "101evler":
            prop_type = getattr(can.property, "property_type", None) if can.property else None
            if prop_type:
                v = await resolve_dest_enum(db, destination=dest, namespace="property_type", source_key=str(prop_type))
                if not v:
                    missing_property_types.add(str(prop_type))
                    ok = False
            else:
                missing_property_types.add("<missing>")
                ok = False

            if can.list_price:
                cur = can.list_price.currency
                v = await resolve_dest_enum(db, destination=dest, namespace="currency", source_key=str(cur))
                if not v:
                    missing_currencies.add(str(cur))
                    ok = False
            else:
                missing_currencies.add("<missing_price>")
                ok = False

            # geo mapping: city/area slugs
            city_slug = _slug(can.address.city) if can.address else ""
            area_slug = _slug(getattr(can.address, "area", None) or "") if can.address else ""
            if not city_slug or not area_slug or not country:
                missing_geo.add(f"{city_slug}:{area_slug}")
                ok = False
            else:
                city = (await db.execute(select(GeoCity).where(
                    GeoCity.country_id == country.id,
                    GeoCity.slug == city_slug,
                ))).scalar_one_or_none()
                if not city:
                    missing_geo.add(f"{city_slug}:{area_slug}")
                    ok = False
                else:
                    area = (await db.execute(select(GeoArea).where(
                        GeoArea.city_id == city.id,
                        GeoArea.slug == area_slug,
                    ))).scalar_one_or_none()
                    if not area:
                        missing_geo.add(f"{city_slug}:{area_slug}")
                        ok = False
                    else:
                        m = (await db.execute(select(DestinationGeoMapping).where(
                            DestinationGeoMapping.destination == dest,
                            DestinationGeoMapping.geo_area_id == area.id,
                        ))).scalar_one_or_none()
                        if not m or not m.destination_area_id:
                            missing_geo.add(f"{city_slug}:{area_slug}")
                            ok = False

        if ok:
            exportable += 1

    return {
        "destination": dest,
        "checked": len(rows),
        "exportable": exportable,
        "missing": {
            "property_types": sorted(missing_property_types),
            "currencies": sorted(missing_currencies),
            "geo_city_area": sorted(missing_geo),
        }
    }
