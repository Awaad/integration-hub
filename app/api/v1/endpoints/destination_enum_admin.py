from app.services import audit
from app.services.auth import Actor
from fastapi import APIRouter, Depends
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.destination_enum_mapping import DestinationEnumMapping
from app.schemas.destination_enum_admin import DestinationEnumUpsert, DestinationEnumBulkUpsert
from app.services.internal_admin import require_internal_admin

router = APIRouter()

@router.put("/admin/destinations/enums", dependencies=[Depends(require_internal_admin)])
async def upsert_destination_enum(body: DestinationEnumUpsert, db: AsyncSession = Depends(get_db), actor: Actor = Depends(require_internal_admin),):
    dest = body.destination.lower().strip()
    ns = body.namespace.lower().strip()
    key = body.source_key.strip()

    stmt = (
        insert(DestinationEnumMapping)
        .values(
            destination=dest,
            namespace=ns,
            source_key=key,
            destination_value=body.destination_value,
            created_by="internal",
            updated_by="internal",
        )
        .on_conflict_do_update(
            constraint="uq_dest_enum_map",
            set_={"destination_value": body.destination_value, "updated_by": "internal"},
        )
        .returning(DestinationEnumMapping)
    )
    row = (await db.execute(stmt)).scalar_one()

    await audit(
        db,
        tenant_id=None,
        partner_id=None,
        actor_api_key_id=getattr(actor, "api_key_id", None),
        action="admin.destination_enum.upsert",
        target_type="destination_enum_mapping",
        target_id=f"{dest}:{ns}:{key}",
        detail={"destination": dest, "namespace": ns, "source_key": key},
    )
    
    await db.commit()
    return {
        "destination": row.destination,
        "namespace": row.namespace,
        "source_key": row.source_key,
        "destination_value": row.destination_value,
    }

@router.post("/admin/destinations/enums/bulk", dependencies=[Depends(require_internal_admin)])
async def bulk_upsert_destination_enums(body: DestinationEnumBulkUpsert, db: AsyncSession = Depends(get_db), actor: Actor = Depends(require_internal_admin),):
    dest = body.destination.lower().strip()
    ns = body.namespace.lower().strip()
    count = 0

    for it in body.items:
        stmt = (
            insert(DestinationEnumMapping)
            .values(
                destination=dest,
                namespace=ns,
                source_key=it.source_key.strip(),
                destination_value=it.destination_value,
                created_by="internal",
                updated_by="internal",
            )
            .on_conflict_do_update(
                constraint="uq_dest_enum_map",
                set_={"destination_value": it.destination_value, "updated_by": "internal"},
            )
        )
        await db.execute(stmt)
        count += 1

    await audit(
        db,
        tenant_id=None,
        partner_id=None,
        actor_api_key_id=getattr(actor, "api_key_id", None),
        action="admin.destination_enums.bulk_upsert",
        target_type="destination_enum_mapping",
        target_id=f"{dest}:{ns}",
        detail={"destination": dest, "namespace": ns, "count": count},
    )

    await db.commit()
    return {"destination": dest, "namespace": ns, "count": count}
