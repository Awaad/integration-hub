from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql import func

from app.models.destination_catalog_set import DestinationCatalogSet
from app.models.destination_catalog_set_item import DestinationCatalogSetItem
from app.models.destination_catalog_set_active import DestinationCatalogSetActive

from app.models.destination_enum_mapping import DestinationEnumMapping
from app.models.destination_geo_mapping import DestinationGeoMapping
from app.models.geo_country import GeoCountry
from app.models.geo_city import GeoCity
from app.models.geo_area import GeoArea


async def activate_catalog_set(
    db: AsyncSession,
    *,
    catalog_set_id: str,
    actor_id: str,
) -> DestinationCatalogSet:
    cs = (await db.execute(select(DestinationCatalogSet).where(DestinationCatalogSet.id == catalog_set_id))).scalar_one()

    if cs.status not in ("pending", "draft"):
        raise ValueError("Catalog set must be pending/draft to activate")

    # normalize scope key (global => "")
    cc = (cs.country_code or "").upper().strip()

    # prefetch country for geo items
    country = None
    if cc:
        country = (await db.execute(
            select(GeoCountry).where(GeoCountry.code == cc)
        )).scalar_one()

    # apply all items into runtime lookup tables
    items = (await db.execute(
        select(DestinationCatalogSetItem).where(DestinationCatalogSetItem.catalog_set_id == catalog_set_id)
    )).scalars().all()


    for it in items:
        if it.kind == "enum":
            if not it.namespace or not it.source_key or not it.destination_value:
                continue
            stmt = (
                insert(DestinationEnumMapping)
                .values(
                    destination=cs.destination,
                    namespace=it.namespace,
                    source_key=it.source_key,
                    destination_value=it.destination_value,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
                .on_conflict_do_update(
                    constraint="uq_dest_enum_map",
                    set_={"destination_value": it.destination_value, "updated_by": actor_id},
                )
            )
            await db.execute(stmt)

        elif it.kind == "geo":
            if not country or not it.geo_key or not it.destination_area_id:
                continue
            if ":" not in it.geo_key:
                continue
            city_slug, area_slug = it.geo_key.split(":", 1)

            city = (await db.execute(select(GeoCity).where(
                GeoCity.country_id == country.id,
                GeoCity.slug == city_slug
            ))).scalar_one_or_none()
            if not city:
                continue

            area = (await db.execute(select(GeoArea).where(
                GeoArea.city_id == city.id,
                GeoArea.slug == area_slug
            ))).scalar_one_or_none()
            if not area:
                continue

            stmt = (
                insert(DestinationGeoMapping)
                .values(
                    destination=cs.destination,
                    geo_country_id=country.id,
                    geo_city_id=city.id,
                    geo_area_id=area.id,
                    destination_area_id=it.destination_area_id,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
                .on_conflict_do_update(
                    constraint="uq_dest_geo_area",
                    set_={"destination_area_id": it.destination_area_id, "updated_by": actor_id},
                )
            )
            await db.execute(stmt)

    # set active pointer
    ptr = (await db.execute
           (select(DestinationCatalogSetActive).where(
        DestinationCatalogSetActive.destination == cs.destination,
        DestinationCatalogSetActive.country_code == cc,
    )
    )).scalar_one_or_none()

    if not ptr:
        ptr = DestinationCatalogSetActive(
            destination=cs.destination,
            country_code=cc,
            active_catalog_set_id=cs.id,
        )
        db.add(ptr)
    else:
        ptr.active_catalog_set_id = cs.id

    cs.status = "active"
    cs.approved_by = actor_id
    cs.approved_at = func.now()
    cs.updated_by = actor_id

    await db.flush()
    return cs
