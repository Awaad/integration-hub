from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.geo_country import GeoCountry
from app.models.geo_city import GeoCity
from app.models.geo_area import GeoArea
from app.models.destination_geo_mapping import DestinationGeoMapping
from app.schemas.geo_admin import (
    GeoCountryUpsert,
    GeoBulkImportCities,
    GeoBulkImportAreas,
    DestinationGeoAreaMappingUpsert,
)
from app.services.internal_admin import require_internal_admin

router = APIRouter()

@router.put("/admin/geo/countries/{code}", dependencies=[Depends(require_internal_admin)])
async def upsert_country(code: str, body: GeoCountryUpsert, db: AsyncSession = Depends(get_db)):
    code_norm = code.strip().upper()
    stmt = (
        insert(GeoCountry)
        .values(code=code_norm, name=body.name)
        .on_conflict_do_update(
            constraint="uq_geo_country_code",
            set_={"name": body.name},
        )
        .returning(GeoCountry)
    )
    row = (await db.execute(stmt)).scalar_one()
    await db.commit()
    return {"id": row.id, "code": row.code, "name": row.name}

@router.post("/admin/geo/cities/bulk", dependencies=[Depends(require_internal_admin)])
async def bulk_import_cities(body: GeoBulkImportCities, db: AsyncSession = Depends(get_db)):
    country = (await db.execute(select(GeoCountry).where(GeoCountry.code == body.country_code.upper().strip()))).scalar_one_or_none()
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")

    inserted = 0
    for c in body.cities:
        stmt = (
            insert(GeoCity)
            .values(country_id=country.id, name=c.name, slug=c.slug.lower().strip())
            .on_conflict_do_update(
                constraint="uq_geo_city_slug",
                set_={"name": c.name},
            )
        )
        await db.execute(stmt)
        inserted += 1

    await db.commit()
    return {"country_code": country.code, "count": inserted}

@router.post("/admin/geo/areas/bulk", dependencies=[Depends(require_internal_admin)])
async def bulk_import_areas(body: GeoBulkImportAreas, db: AsyncSession = Depends(get_db)):
    country = (await db.execute(select(GeoCountry).where(GeoCountry.code == body.country_code.upper().strip()))).scalar_one_or_none()
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")

    city = (await db.execute(select(GeoCity).where(
        GeoCity.country_id == country.id,
        GeoCity.slug == body.city_slug.lower().strip(),
    ))).scalar_one_or_none()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")

    inserted = 0
    for a in body.areas:
        stmt = (
            insert(GeoArea)
            .values(city_id=city.id, name=a.name, slug=a.slug.lower().strip())
            .on_conflict_do_update(
                constraint="uq_geo_area_slug",
                set_={"name": a.name},
            )
        )
        await db.execute(stmt)
        inserted += 1

    await db.commit()
    return {"country_code": country.code, "city_slug": city.slug, "count": inserted}

@router.put("/admin/geo/destinations/area-mapping", dependencies=[Depends(require_internal_admin)])
async def upsert_destination_area_mapping(body: DestinationGeoAreaMappingUpsert, db: AsyncSession = Depends(get_db)):
    dest = body.destination.lower().strip()

    country = (await db.execute(select(GeoCountry).where(GeoCountry.code == body.country_code.upper().strip()))).scalar_one_or_none()
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")

    city = (await db.execute(select(GeoCity).where(
        GeoCity.country_id == country.id,
        GeoCity.slug == body.city_slug.lower().strip(),
    ))).scalar_one_or_none()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")

    area = (await db.execute(select(GeoArea).where(
        GeoArea.city_id == city.id,
        GeoArea.slug == body.area_slug.lower().strip(),
    ))).scalar_one_or_none()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    stmt = (
        insert(DestinationGeoMapping)
        .values(
            destination=dest,
            geo_country_id=country.id,
            geo_city_id=city.id,
            geo_area_id=area.id,
            destination_city_id=body.destination_city_id,
            destination_area_id=body.destination_area_id,
            created_by="internal",
            updated_by="internal",
        )
        .on_conflict_do_update(
            constraint="uq_dest_geo_area",
            set_={
                "destination_city_id": body.destination_city_id,
                "destination_area_id": body.destination_area_id,
                "updated_by": "internal",
            },
        )
        .returning(DestinationGeoMapping)
    )

    row = (await db.execute(stmt)).scalar_one()
    await db.commit()

    return {
        "destination": row.destination,
        "country_code": country.code,
        "city_slug": city.slug,
        "area_slug": area.slug,
        "destination_city_id": row.destination_city_id,
        "destination_area_id": row.destination_area_id,
    }
