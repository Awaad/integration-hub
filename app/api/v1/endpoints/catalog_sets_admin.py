from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.db import get_db
from app.services.internal_admin import require_internal_admin
from app.services.audit import audit
from app.services.catalog_sets import submit_catalog_set, reject_catalog_set, rollback_active_catalog_set, activate_catalog_set

from app.models.destination_catalog_set import DestinationCatalogSet
from app.models.destination_catalog_set_item import DestinationCatalogSetItem

from app.services.catalog_sets_builder import create_draft_catalog_set_from_run


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
                namespace=(it.get("namespace") or "").lower().strip(),
                source_key=(it.get("source_key") or "").strip(),
                destination_value=(it.get("destination_value") or "").strip(),
                meta=it.get("meta") or {},
            ))
        elif kind == "geo":
            db.add(DestinationCatalogSetItem(
                catalog_set_id=catalog_set_id,
                kind="geo",
                geo_key=(it.get("geo_key") or "").strip(),
                geo_country_code=str(it.get("geo_country_code") or cs.country_code or "").upper().strip(),
                destination_area_id=(it.get("destination_area_id") or "").strip(),
                meta=it.get("meta") or {},
            ))
        else:
            raise HTTPException(status_code=422, detail=f"invalid kind: {kind}")

    await db.commit()
    return {"ok": True}



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



@router.post("/admin/destinations/{destination}/catalog-sets/from-import/{run_id}", dependencies=[Depends(require_internal_admin)])
async def draft_from_import(destination: str, run_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    name = body.get("name")
    try:
        cs = await create_draft_catalog_set_from_run(
            db,
            destination=destination,   
            run_id=run_id,
            name=name,
            actor_id="internal",
        )
        await audit(
            db,
            tenant_id=None,
            partner_id=None,
            actor_api_key_id="internal",
            action="catalog_set.draft_from_import",
            target_type="destination_catalog_set",
            target_id=cs.id,
            detail={"destination": cs.destination, "run_id": run_id},
        )
        await db.commit()
        return {"id": cs.id, "status": cs.status, "name": cs.name}
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/admin/catalog-sets/{catalog_set_id}:submit", dependencies=[Depends(require_internal_admin)])
async def submit_set(catalog_set_id: str, db: AsyncSession = Depends(get_db)):
    cs = await submit_catalog_set(db, catalog_set_id=catalog_set_id, actor_id="internal")

    await audit(db, None, None, "internal", "catalog_set.submitted", "destination_catalog_set", cs.id, {"destination": cs.destination})
    await db.commit()
    return {"id": cs.id, "status": cs.status}



@router.post("/admin/catalog-sets/{catalog_set_id}:approve", dependencies=[Depends(require_internal_admin)])
async def approve_set(catalog_set_id: str, db: AsyncSession = Depends(get_db)):
    cs = await activate_catalog_set(db, catalog_set_id=catalog_set_id, actor_id="internal")

    await audit(db, None, None, "internal", "catalog_set.approved", "destination_catalog_set", cs.id, {"destination": cs.destination, "country_code": cs.country_code})
    await db.commit()
    return {"id": cs.id, "status": cs.status}



@router.post("/admin/catalog-sets/{catalog_set_id}:reject", dependencies=[Depends(require_internal_admin)])
async def reject_set(catalog_set_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    reason = body.get("reason")
    cs = await reject_catalog_set(db, catalog_set_id=catalog_set_id, actor_id="internal", reason=reason)
    await audit(db, None, None, "internal", "catalog_set.rejected", "destination_catalog_set", cs.id, {"reason": reason})
    await db.commit()
    return {"id": cs.id, "status": cs.status}



@router.post("/admin/destinations/{destination}/catalog-sets:rollback", dependencies=[Depends(require_internal_admin)])
async def rollback_set(destination: str, body: dict, db: AsyncSession = Depends(get_db)):
    dest = destination.lower().strip()
    cc = body.get("country_code")
    to_id = body.get("to_catalog_set_id")
    if not to_id:
        raise HTTPException(status_code=422, detail="to_catalog_set_id required")

    cs = await rollback_active_catalog_set(db, destination=dest, country_code=(cc.upper().strip() if cc else None), to_catalog_set_id=to_id, actor_id="internal")
    await audit(db, None, None, "internal", "catalog_set.rollback", "destination_catalog_set", cs.id, {"destination": cs.destination, "country_code": cs.country_code})
    await db.commit()
    return {"id": cs.id, "status": cs.status}