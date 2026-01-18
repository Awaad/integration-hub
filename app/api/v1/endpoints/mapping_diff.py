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
from app.destinations.mapping_registry import get_mapping_plugin
from app.destinations.mapping_base import MappingKeySet

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

    plugin = get_mapping_plugin(dest)

    agg_enum: dict[str, set[str]] = {}
    agg_geo: set[str] = set()
    

    for r in rows:
        can = ListingCanonicalV1.model_validate(r.payload)
        ks = plugin.required_mapping_keys(can)
        for ns, skeys in ks.enum_keys.items():
            agg_enum.setdefault(ns, set()).update(skeys)
        agg_geo |= set(ks.geo_keys)

    check = await plugin.check_mappings(db=db, tenant_id=actor.tenant_id, partner_id=partner_id, keys=MappingKeySet(agg_enum, agg_geo))
    return {
    "destination": dest,
    "checked": len(rows),
    "missing": {
        "enums": {ns: sorted(list(v)) for ns, v in check.missing.enum_keys.items()},
        "geo": sorted(list(check.missing.geo_keys)),
    },
    "warnings": check.warnings,
    }
