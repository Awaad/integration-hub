from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.services.internal_admin import require_internal_admin

from app.schemas.mapping_diff import DestinationEnumDictImport, DestinationAreaDictImport
from app.models.destination_enum_mapping import DestinationEnumMapping
from app.models.geo_country import GeoCountry
from app.models.geo_city import GeoCity
from app.models.geo_area import GeoArea
from app.models.destination_geo_mapping import DestinationGeoMapping

router = APIRouter()

def _slug(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "-")

@router.post("/admin/import/destination-enums", dependencies=[Depends(require_internal_admin)])
async def import_destination_enums(body: DestinationEnumDictImport, db: AsyncSession = Depends(get_db)):
    dest = body.destination.lower().strip()
    ns = body.namespace.lower().strip()

    count = 0
    for k, v in body.mappings.items():
        stmt = (
            insert(DestinationEnumMapping)
            .values(
                destination=dest,
                namespace=ns,
                source_key=str(k).strip(),
                destination_value=str(v).strip(),
                created_by="internal",
                updated_by="internal",
            )
            .on_conflict_do_update(
                constraint="uq_dest_enum_map",
                set_={"destination_value": str(v).strip(), "updated_by": "internal"},
            )
        )
        await db.execute(stmt)
        count += 1

    await db.commit()
    return {"destination": dest, "namespace": ns, "count": count}

@router.post("/admin/import/destination-areas", dependencies=[Depends(require_internal_admin)])
async def import_destination_areas(body: DestinationAreaDictImport, db: AsyncSession = Depends(get_db)):
    dest = body.destination.lower().strip()
    country = (await db.execute(select(GeoCountry).where(GeoCountry.code == body.country_code.upper().strip()))).scalar_one_or_none()
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")

    count = 0
    for k, area_id in body.mappings.items():
        # key: city_slug:area_slug
        if ":" not in k:
            continue
        city_slug, area_slug = k.split(":", 1)
        city_slug = _slug(city_slug)
        area_slug = _slug(area_slug)

        city = (await db.execute(select(GeoCity).where(GeoCity.country_id == country.id, GeoCity.slug == city_slug))).scalar_one_or_none()
        if not city:
            continue
        area = (await db.execute(select(GeoArea).where(GeoArea.city_id == city.id, GeoArea.slug == area_slug))).scalar_one_or_none()
        if not area:
            continue

        stmt = (
            insert(DestinationGeoMapping)
            .values(
                destination=dest,
                geo_country_id=country.id,
                geo_city_id=city.id,
                geo_area_id=area.id,
                destination_area_id=str(area_id).strip(),
                created_by="internal",
                updated_by="internal",
            )
            .on_conflict_do_update(
                constraint="uq_dest_geo_area",
                set_={"destination_area_id": str(area_id).strip(), "updated_by": "internal"},
            )
        )
        await db.execute(stmt)
        count += 1

    await db.commit()
    return {"destination": dest, "country_code": country.code, "count": count}
