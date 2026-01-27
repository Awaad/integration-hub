from __future__ import annotations
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.destination_catalog_import_run import DestinationCatalogImportRun
from app.models.destination_catalog_import_item import DestinationCatalogImportItem
from app.models.destination_catalog_set import DestinationCatalogSet
from app.models.destination_catalog_set_item import DestinationCatalogSetItem


async def create_draft_catalog_set_from_run(
    db: AsyncSession,
    *,
    destination: str,
    run_id: str,
    name: str | None,
    actor_id: str,
) -> DestinationCatalogSet:
    dest = destination.lower().strip()

    run = (await db.execute(
        select(DestinationCatalogImportRun)
        .where(DestinationCatalogImportRun.id == run_id)
        .with_for_update()
    )).scalar_one()

    if destination and run.destination.lower().strip() != dest:
        raise ValueError("Import run destination mismatch")

    # If already linked, return the same set (idempotent)
    if getattr(run, "catalog_set_id", None):
        cs = (
            await db.execute(
                select(DestinationCatalogSet).where(DestinationCatalogSet.id == run.catalog_set_id)
            )
        ).scalar_one()
        return cs
    
    cc = (run.country_code.upper().strip() if run.country_code else None)
    ns = (run.namespace.lower().strip() if run.namespace else None)

    scope = ns or cc or "global"

    set_name = name or f"{dest}_{run.kind}_{scope}_{run_id}"

    cs = DestinationCatalogSet(
        destination=dest,
        name=set_name,
        country_code=cc,
        status="draft",
        change_note=json.dumps({"run_id": run.id, "source": run.source, "summary": run.summary}, ensure_ascii=False),
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(cs)
    await db.flush()

    items = (await db.execute(select(DestinationCatalogImportItem).where(
        DestinationCatalogImportItem.run_id == run_id,
        DestinationCatalogImportItem.action.in_(["insert", "update"]),
    ))).scalars().all()

    for it in items:
        if run.kind == "enum":
            db.add(DestinationCatalogSetItem(
                catalog_set_id=cs.id,
                kind="enum",
                namespace=ns,
                source_key=it.key,
                destination_value=it.value,
                meta={"existing_value": it.existing_value, "action": it.action},
            ))
        else:
            # geo
            db.add(DestinationCatalogSetItem(
                catalog_set_id=cs.id,
                kind="geo",
                geo_key=it.key,  # city:area
                geo_country_code=cc,
                destination_area_id=it.value,
                meta={"existing_value": it.existing_value, "action": it.action, **(it.detail or {})},
            ))

    run.catalog_set_id = cs.id
    run.updated_by = actor_id
    await db.flush()
    return cs
