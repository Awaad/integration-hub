from __future__ import annotations
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.models.destination_catalog_import_run import DestinationCatalogImportRun
from app.models.destination_catalog_import_item import DestinationCatalogImportItem
from app.models.destination_enum_mapping import DestinationEnumMapping
from app.models.destination_geo_mapping import DestinationGeoMapping
from app.models.geo_country import GeoCountry
from app.models.geo_city import GeoCity
from app.models.geo_area import GeoArea


def _slug(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "-")


async def preview_enum_import(
    db: AsyncSession,
    *,
    destination: str,
    namespace: str,
    items: list[tuple[str, str]],  # (source_key, destination_value)
    source: str | None,
    actor_id: str,
) -> DestinationCatalogImportRun:
    dest = destination.lower().strip()
    ns = namespace.lower().strip()

    run = DestinationCatalogImportRun(
        destination=dest,
        kind="enum",
        namespace=ns,
        country_code=None,
        source=source,
        status="previewed",
        summary={},
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(run)
    await db.flush()

    # Load existing mappings for the namespace in one query
    existing_rows = (await db.execute(
        select(DestinationEnumMapping.source_key, DestinationEnumMapping.destination_value).where(
            DestinationEnumMapping.destination == dest,
            DestinationEnumMapping.namespace == ns,
        )
    )).all()
    existing = {k: v for (k, v) in existing_rows}

    to_insert = to_update = noop = invalid = 0

    for skey, dval in items:
        skey_n = str(skey).strip()
        dval_n = str(dval).strip()
        if not skey_n or not dval_n:
            invalid += 1
            db.add(DestinationCatalogImportItem(
                run_id=run.id,
                key=skey_n or "<empty>",
                value=dval_n or None,
                existing_value=None,
                action="invalid",
                detail={"reason": "empty key/value"},
            ))
            continue

        ex = existing.get(skey_n)
        if ex is None:
            to_insert += 1
            action = "insert"
        elif ex != dval_n:
            to_update += 1
            action = "update"
        else:
            noop += 1
            action = "noop"

        db.add(DestinationCatalogImportItem(
            run_id=run.id,
            key=skey_n,
            value=dval_n,
            existing_value=ex,
            action=action,
            detail={},
        ))

    run.summary = {"to_insert": to_insert, "to_update": to_update, "unchanged": noop, "invalid": invalid}
    await db.flush()
    return run


async def apply_enum_import(
    db: AsyncSession,
    *,
    run: DestinationCatalogImportRun,
    actor_id: str,
) -> None:
    assert run.kind == "enum"
    dest = run.destination
    ns = run.namespace or ""

    rows = (await db.execute(
        select(DestinationCatalogImportItem).where(
            DestinationCatalogImportItem.run_id == run.id,
            DestinationCatalogImportItem.action.in_(["insert", "update"]),
        )
    )).scalars().all()

    count = 0
    for it in rows:
        stmt = (
            insert(DestinationEnumMapping)
            .values(
                destination=dest,
                namespace=ns,
                source_key=it.key,
                destination_value=it.value,
                created_by=actor_id,
                updated_by=actor_id,
            )
            .on_conflict_do_update(
                constraint="uq_dest_enum_map",
                set_={"destination_value": it.value, "updated_by": actor_id},
            )
        )
        await db.execute(stmt)
        count += 1

    run.status = "applied"
    run.updated_by = actor_id
    run.summary = {**(run.summary or {}), "applied": count}
    await db.flush()


async def preview_geo_import(
    db: AsyncSession,
    *,
    destination: str,
    country_code: str,
    items: list[tuple[str, str, str]],  # (city_slug, area_slug, destination_area_id)
    source: str | None,
    actor_id: str,
) -> DestinationCatalogImportRun:
    dest = destination.lower().strip()
    cc = country_code.upper().strip()

    run = DestinationCatalogImportRun(
        destination=dest,
        kind="geo",
        namespace=None,
        country_code=cc,
        source=source,
        status="previewed",
        summary={},
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(run)
    await db.flush()

    country = (await db.execute(select(GeoCountry).where(GeoCountry.code == cc))).scalar_one_or_none()

    # If country missing, all items invalid (still record run/items for visibility)
    if not country:
        invalid = len(items)
        for city_slug, area_slug, d_area_id in items:
            db.add(DestinationCatalogImportItem(
                run_id=run.id,
                key=f"{_slug(city_slug)}:{_slug(area_slug)}",
                value=str(d_area_id).strip(),
                existing_value=None,
                action="invalid",
                detail={"reason": f"country {cc} not found"},
            ))
        run.summary = {"to_insert": 0, "to_update": 0, "unchanged": 0, "invalid": invalid}
        await db.flush()
        return run

    # Build lookup of geo_area_id -> destination_area_id for this destination
    existing_rows = (await db.execute(
        select(DestinationGeoMapping.geo_area_id, DestinationGeoMapping.destination_area_id).where(
            DestinationGeoMapping.destination == dest,
            DestinationGeoMapping.geo_country_id == country.id,
        )
    )).all()
    existing_by_area_id = {gid: did for (gid, did) in existing_rows}

    to_insert = to_update = noop = invalid = 0

    for city_slug, area_slug, d_area_id in items:
        cslug = _slug(city_slug)
        aslug = _slug(area_slug)
        d_area = str(d_area_id).strip()
        key = f"{cslug}:{aslug}"

        if not cslug or not aslug or not d_area:
            invalid += 1
            db.add(DestinationCatalogImportItem(
                run_id=run.id,
                key=key or "<empty>",
                value=d_area or None,
                existing_value=None,
                action="invalid",
                detail={"reason": "empty city/area/id"},
            ))
            continue

        city = (await db.execute(select(GeoCity).where(
            GeoCity.country_id == country.id, GeoCity.slug == cslug
        ))).scalar_one_or_none()
        if not city:
            invalid += 1
            db.add(DestinationCatalogImportItem(
                run_id=run.id,
                key=key,
                value=d_area,
                existing_value=None,
                action="invalid",
                detail={"reason": f"GeoCity slug not found: {cslug}"},
            ))
            continue

        area = (await db.execute(select(GeoArea).where(
            GeoArea.city_id == city.id, GeoArea.slug == aslug
        ))).scalar_one_or_none()
        if not area:
            invalid += 1
            db.add(DestinationCatalogImportItem(
                run_id=run.id,
                key=key,
                value=d_area,
                existing_value=None,
                action="invalid",
                detail={"reason": f"GeoArea slug not found: {aslug}"},
            ))
            continue

        ex = existing_by_area_id.get(area.id)
        if ex is None:
            to_insert += 1
            action = "insert"
        elif ex != d_area:
            to_update += 1
            action = "update"
        else:
            noop += 1
            action = "noop"

        db.add(DestinationCatalogImportItem(
            run_id=run.id,
            key=key,
            value=d_area,
            existing_value=ex,
            action=action,
            detail={"geo_area_id": area.id, "geo_city_id": city.id, "geo_country_id": country.id},
        ))

    run.summary = {"to_insert": to_insert, "to_update": to_update, "unchanged": noop, "invalid": invalid}
    await db.flush()
    return run


async def apply_geo_import(
    db: AsyncSession,
    *,
    run: DestinationCatalogImportRun,
    actor_id: str,
) -> None:
    assert run.kind == "geo"
    dest = run.destination
    cc = run.country_code or ""

    country = (await db.execute(select(GeoCountry).where(GeoCountry.code == cc))).scalar_one()

    rows = (await db.execute(
        select(DestinationCatalogImportItem).where(
            DestinationCatalogImportItem.run_id == run.id,
            DestinationCatalogImportItem.action.in_(["insert", "update"]),
        )
    )).scalars().all()

    count = 0
    for it in rows:
        # geo ids were stored in detail during preview
        geo_area_id = (it.detail or {}).get("geo_area_id")
        geo_city_id = (it.detail or {}).get("geo_city_id")
        if not geo_area_id or not geo_city_id:
            continue

        stmt = (
            insert(DestinationGeoMapping)
            .values(
                destination=dest,
                geo_country_id=country.id,
                geo_city_id=geo_city_id,
                geo_area_id=geo_area_id,
                destination_area_id=it.value,
                created_by=actor_id,
                updated_by=actor_id,
            )
            .on_conflict_do_update(
                constraint="uq_dest_geo_area",
                set_={"destination_area_id": it.value, "updated_by": actor_id},
            )
        )
        await db.execute(stmt)
        count += 1

    run.status = "applied"
    run.updated_by = actor_id
    run.summary = {**(run.summary or {}), "applied": count}
    await db.flush()
