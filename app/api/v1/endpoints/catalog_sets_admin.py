from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.db import get_db
from app.services.internal_admin import require_internal_admin
from app.services.audit import audit
from app.services.catalog_sets import activate_catalog_set

from app.models.destination_catalog_set import DestinationCatalogSet
from app.models.destination_catalog_set_item import DestinationCatalogSetItem

router = APIRouter()

@router.post("/admin/destinations/{destination}/catalog-sets", dependencies=[Depends(require_internal_admin)])
async def create_catalog_set(destination: str, body: dict, db: AsyncSession = Depends(get_db)):
    dest = destination.lower().strip()
    name = str(body.get("name") or "").strip()
    country_code_raw = body.get("country_code")
    country_code = (str(country_code_raw).upper().strip() if country_code_raw else None)
    change_note = body.get("change_note")

    if not name:
        raise HTTPException(status_code=422, detail="name is required")

    cs = DestinationCatalogSet(
        destination=dest,
        name=name,
        country_code=country_code,
        status="draft",
        change_note=change_note,
        created_by="internal",
        updated_by="internal",
    )
    db.add(cs)
    await db.commit()
    return {"id": cs.id, "destination": cs.destination, "name": cs.name, "country_code": cs.country_code, "status": cs.status}

@router.post("/admin/catalog-sets/{catalog_set_id}/items", dependencies=[Depends(require_internal_admin)])
async def add_items(catalog_set_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    items = body.get("items") or []
    if not isinstance(items, list):
        raise HTTPException(status_code=422, detail="items must be a list")

    cs = (await db.execute(select(DestinationCatalogSet).where(DestinationCatalogSet.id == catalog_set_id))).scalar_one_or_none()
    if not cs:
        raise HTTPException(status_code=404, detail="catalog set not found")
    if cs.status != "draft":
        raise HTTPException(status_code=409, detail="only draft sets can be edited")

    for it in items:
        kind = (it.get("kind") or "").strip()
        if kind == "enum":
            db.add(DestinationCatalogSetItem(
                catalog_set_id=catalog_set_id,
                kind="enum",
                namespace=(it.get("namespace") or "").strip(),
                source_key=(it.get("source_key") or "").strip(),
                destination_value=(it.get("destination_value") or "").strip(),
                meta=it.get("meta") or {},
            ))
        elif kind == "geo":
            db.add(DestinationCatalogSetItem(
                catalog_set_id=catalog_set_id,
                kind="geo",
                geo_key=(it.get("geo_key") or "").strip(),
                geo_country_code=(it.get("geo_country_code") or cs.country_code),
                destination_area_id=(it.get("destination_area_id") or "").strip(),
                meta=it.get("meta") or {},
            ))
        else:
            raise HTTPException(status_code=422, detail=f"invalid kind: {kind}")

    await db.commit()
    return {"ok": True}

@router.post("/admin/catalog-sets/{catalog_set_id}:activate", dependencies=[Depends(require_internal_admin)])
async def activate_set(catalog_set_id: str, db: AsyncSession = Depends(get_db)):
    try:
        cs = await activate_catalog_set(db, catalog_set_id=catalog_set_id, actor_id="internal")
        await audit(
            db,
            tenant_id=None,
            partner_id=None,
            actor_api_key_id="internal",
            action="catalog_set.activated",
            target_type="destination_catalog_set",
            target_id=cs.id,
            detail={"destination": cs.destination, "country_code": cs.country_code},
        )
        await db.commit()
        return {"id": cs.id, "status": cs.status}
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(e))

@router.get("/admin/destinations/{destination}/catalog-sets", dependencies=[Depends(require_internal_admin)])
async def list_sets(destination: str, db: AsyncSession = Depends(get_db)):
    dest = destination.lower().strip()
    rows = (await db.execute(
        select(DestinationCatalogSet)
        .where(DestinationCatalogSet.destination == dest)
        .order_by(desc(DestinationCatalogSet.created_at))
        .limit(50)
    )).scalars().all()

    return [{
        "id": r.id,
        "name": r.name,
        "country_code": r.country_code,
        "status": r.status,
        "created_at": r.created_at,
        "approved_at": r.approved_at,
    } for r in rows]
