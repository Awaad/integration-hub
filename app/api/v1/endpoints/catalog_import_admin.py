from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db import get_db
from app.services.internal_admin import require_internal_admin
from app.services.audit import audit

from app.schemas.catalog_import import (
    EnumCatalogImportRequest,
    GeoCatalogImportRequest,
    CatalogImportResponse,
)
from app.models.destination_catalog_import_run import DestinationCatalogImportRun
from app.services.catalog_importer import (
    preview_enum_import, apply_enum_import,
    preview_geo_import, apply_geo_import,
)

router = APIRouter()

@router.post(
    "/admin/destinations/{destination}/catalogs/enums/{namespace}:preview",
    response_model=CatalogImportResponse,
    dependencies=[Depends(require_internal_admin)],
)
async def preview_enum(destination: str, namespace: str, body: EnumCatalogImportRequest, db: AsyncSession = Depends(get_db)):
    pairs = [(i.source_key, i.destination_value) for i in body.items]
    run = await preview_enum_import(
        db,
        destination=destination,
        namespace=namespace,
        items=pairs,
        source=body.source,
        actor_id="internal",
    )
    await db.commit()
    return CatalogImportResponse(
        run_id=run.id, destination=run.destination, kind=run.kind, namespace=run.namespace,
        country_code=run.country_code, status=run.status, summary=run.summary,
    )

@router.post(
    "/admin/destinations/{destination}/catalogs/enums/{namespace}:apply",
    response_model=CatalogImportResponse,
    dependencies=[Depends(require_internal_admin)],
)
async def apply_enum(destination: str, namespace: str, body: EnumCatalogImportRequest, db: AsyncSession = Depends(get_db)):
    pairs = [(i.source_key, i.destination_value) for i in body.items]
    run = await preview_enum_import(
        db,
        destination=destination,
        namespace=namespace,
        items=pairs,
        source=body.source,
        actor_id="internal",
    )
    await apply_enum_import(db, run=run, actor_id="internal")
    await audit(
        db,
        tenant_id=None,
        partner_id=None,
        actor_api_key_id="internal",
        action="catalog.enum.apply",
        target_type="destination",
        target_id=run.destination,
        detail={"namespace": run.namespace, "summary": run.summary, "source": run.source},
    )
    await db.commit()
    return CatalogImportResponse(
        run_id=run.id, destination=run.destination, kind=run.kind, namespace=run.namespace,
        country_code=run.country_code, status=run.status, summary=run.summary,
    )

@router.post(
    "/admin/destinations/{destination}/catalogs/areas:preview",
    response_model=CatalogImportResponse,
    dependencies=[Depends(require_internal_admin)],
)
async def preview_areas(destination: str, body: GeoCatalogImportRequest, db: AsyncSession = Depends(get_db)):
    triplets = [(i.city_slug, i.area_slug, i.destination_area_id) for i in body.items]
    run = await preview_geo_import(
        db,
        destination=destination,
        country_code=body.country_code,
        items=triplets,
        source=body.source,
        actor_id="internal",
    )
    await db.commit()
    return CatalogImportResponse(
        run_id=run.id, destination=run.destination, kind=run.kind, namespace=run.namespace,
        country_code=run.country_code, status=run.status, summary=run.summary,
    )

@router.post(
    "/admin/destinations/{destination}/catalogs/areas:apply",
    response_model=CatalogImportResponse,
    dependencies=[Depends(require_internal_admin)],
)
async def apply_areas(destination: str, body: GeoCatalogImportRequest, db: AsyncSession = Depends(get_db)):
    triplets = [(i.city_slug, i.area_slug, i.destination_area_id) for i in body.items]
    run = await preview_geo_import(
        db,
        destination=destination,
        country_code=body.country_code,
        items=triplets,
        source=body.source,
        actor_id="internal",
    )
    await apply_geo_import(db, run=run, actor_id="internal")
    await audit(
        db,
        tenant_id=None,
        partner_id=None,
        actor_api_key_id="internal",
        action="catalog.geo.apply",
        target_type="destination",
        target_id=run.destination,
        detail={"country_code": run.country_code, "summary": run.summary, "source": run.source},
    )
    await db.commit()
    return CatalogImportResponse(
        run_id=run.id, destination=run.destination, kind=run.kind, namespace=run.namespace,
        country_code=run.country_code, status=run.status, summary=run.summary,
    )

@router.get(
    "/admin/catalog-import-runs/{run_id}",
    dependencies=[Depends(require_internal_admin)],
)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = (await db.execute(select(DestinationCatalogImportRun).where(DestinationCatalogImportRun.id == run_id))).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "id": run.id,
        "destination": run.destination,
        "kind": run.kind,
        "namespace": run.namespace,
        "country_code": run.country_code,
        "source": run.source,
        "status": run.status,
        "summary": run.summary,
        "error": run.error,
        "created_at": run.created_at,
    }
