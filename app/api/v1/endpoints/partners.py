from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.core.db import get_db
from app.core.security import generate_api_key
from app.models.tenant import Tenant
from app.models.partner import Partner
from app.models.api_key import ApiKey
from app.schemas.partner import PartnerCreate, PartnerBootstrapOut, PartnerRotateKeyOut
from app.services.internal_admin import require_internal_admin
from app.core.ids import gen_id


log = logging.getLogger(__name__)
router = APIRouter()

@router.post("/partners/bootstrap", response_model=PartnerBootstrapOut, dependencies=[Depends(require_internal_admin)])
async def bootstrap_partner(payload: PartnerCreate, db: AsyncSession = Depends(get_db)) -> PartnerBootstrapOut:
    """
    Phase 0 bootstrap endpoint.
    In production, this would be internal-only (ops/admin) and protected by OIDC.
    """
    # Internal-only: we mark audit with "internal"
    # Generate IDs first so we can reference them safely
    tenant_id = gen_id("tnt")
    partner_id = gen_id("prt")

    tenant = Tenant(id=tenant_id, name=payload.tenant_name, created_by="internal", updated_by="internal")
    partner = Partner(id=partner_id, tenant_id=tenant.id, name=payload.partner_name, created_by="internal", updated_by="internal")

    admin_key = generate_api_key()
    key_row = ApiKey(
        tenant_id=tenant.id,
        partner_id=partner.id,
        role="partner_admin",
        agent_id=None,
        key_prefix=admin_key.prefix,
        key_hash=admin_key.hashed,
        is_active=True,
        created_by="internal",
        updated_by="internal",
    )

    try:
        db.add(tenant)
        db.add(partner)
        await db.flush()  # ensures tenant + partner are inserted first (within txn)
        db.add(key_row)
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        log.exception("bootstrap failed: integrity error")
        raise HTTPException(status_code=409, detail="Constraint violation")


    return PartnerBootstrapOut(
        tenant_id=tenant.id,
        partner_id=partner.id,
        partner_admin_api_key=admin_key.plain,
    )


@router.post(
    "/partners/{partner_id}/rotate-admin-key",
    response_model=PartnerRotateKeyOut,
    dependencies=[Depends(require_internal_admin)],
)
async def rotate_partner_admin_key(partner_id: str, db: AsyncSession = Depends(get_db)) -> PartnerBootstrapOut:
    # Ensure partner exists and get tenant_id
    partner = (
        await db.execute(select(Partner).where(Partner.id == partner_id))
    ).scalar_one_or_none()
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")

    # Disable previous admin keys
    await db.execute(
        update(ApiKey)
        .where(ApiKey.partner_id == partner_id, ApiKey.role == "partner_admin", ApiKey.is_active == True)  # noqa: E712
        .values(is_active=False, updated_by="internal")
    )

    # Create new key
    admin_key = generate_api_key()
    key_row = ApiKey(
        tenant_id=partner.tenant_id,
        partner_id=partner_id,
        role="partner_admin",
        agent_id=None,
        key_prefix=admin_key.prefix,
        key_hash=admin_key.hashed,
        is_active=True,
        created_by="internal",
        updated_by="internal",
    )

    try:
        db.add(key_row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        log.exception("rotate admin key failed")
        raise HTTPException(status_code=409, detail="Constraint violation")

    return PartnerRotateKeyOut(
        tenant_id=partner.tenant_id,
        partner_id=partner_id,
        partner_admin_api_key=admin_key.plain,
    )