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



def _slug(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "-")


def _cc_key(country_code: str | None) -> str:
    # DB key convention: global scope => ""
    return (country_code or "").upper().strip()


async def activate_catalog_set(
    db: AsyncSession,
    *,
    catalog_set_id: str,
    actor_id: str,
) -> DestinationCatalogSet:
    cs = (await db.execute(select(DestinationCatalogSet).where(DestinationCatalogSet.id == catalog_set_id))).scalar_one()

    if cs.status not in ("pending", "draft"):
        raise ValueError("Catalog set must be pending/draft to activate")

    dest = cs.destination.lower().strip()
    cc = _cc_key(cs.country_code)

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
            ns = (it.namespace or "").lower().strip()
            skey = (it.source_key or "").strip()
            dval = (it.destination_value or "").strip()

            if not ns or not skey or not dval:
                continue

            stmt = (
                insert(DestinationEnumMapping)
                .values(
                    destination=dest,
                    namespace=ns,
                    source_key=skey,
                    destination_value=dval,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
                .on_conflict_do_update(
                    constraint="uq_dest_enum_map",
                    set_={"destination_value": dval, "updated_by": actor_id},
                )
            )
            await db.execute(stmt)

        elif it.kind == "geo":
            if not country:
                continue
            
            geo_key = (it.geo_key or "").strip()
            d_area_id = (it.destination_area_id or "").strip()
            if not geo_key or not d_area_id or ":" not in geo_key:
                continue

            city_slug, area_slug = geo_key.split(":", 1)

            city_slug = _slug(city_slug)
            area_slug = _slug(area_slug)

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
                    destination=dest,
                    geo_country_id=country.id,
                    geo_city_id=city.id,
                    geo_area_id=area.id,
                    destination_area_id=d_area_id,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
                .on_conflict_do_update(
                    constraint="uq_dest_geo_area",
                    set_={"destination_area_id": d_area_id, "updated_by": actor_id},
                )
            )
            await db.execute(stmt)

    # set active pointer
    ptr = (await db.execute
           (select(DestinationCatalogSetActive).where(
        DestinationCatalogSetActive.destination == dest,
        DestinationCatalogSetActive.country_code == cc,
    )
    )).scalar_one_or_none()

    if not ptr:
        ptr = DestinationCatalogSetActive(
            destination=dest,
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


async def submit_catalog_set(db: AsyncSession, *, catalog_set_id: str, actor_id: str) -> DestinationCatalogSet:
    cs = (await db.execute(select(DestinationCatalogSet).where(DestinationCatalogSet.id == catalog_set_id))).scalar_one()
    if cs.status != "draft":
        raise ValueError("Only draft can be submitted")
    cs.status = "pending"
    cs.updated_by = actor_id
    await db.flush()
    return cs

async def reject_catalog_set(db: AsyncSession, *, catalog_set_id: str, actor_id: str, reason: str | None) -> DestinationCatalogSet:
    cs = (await db.execute(select(DestinationCatalogSet).where(DestinationCatalogSet.id == catalog_set_id))).scalar_one()
    if cs.status != "pending":
        raise ValueError("Only pending can be rejected")
    cs.status = "rejected"
    cs.updated_by = actor_id
    if reason:
        cs.change_note = (cs.change_note or "") + f"\nREJECT_REASON: {reason}"
    await db.flush()
    return cs

async def rollback_active_catalog_set(
    db: AsyncSession,
    *,
    destination: str,
    country_code: str | None,
    to_catalog_set_id: str,
    actor_id: str,
) -> DestinationCatalogSet:
    dest = destination.lower().strip()
    cc = (country_code.upper().strip() if country_code else None)

    target = (await db.execute(select(DestinationCatalogSet).where(DestinationCatalogSet.id == to_catalog_set_id))).scalar_one()
    
    if target.destination.lower().strip() != dest:
        raise ValueError("Catalog set destination mismatch")

    if _cc_key(target.country_code) != cc:
        raise ValueError("Catalog set country_code mismatch")

    return await activate_catalog_set(db, catalog_set_id=to_catalog_set_id, actor_id=actor_id)