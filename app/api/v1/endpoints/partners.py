from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import generate_api_key
from app.models.tenant import Tenant
from app.models.partner import Partner
from app.models.api_key import ApiKey
from app.schemas.partner import PartnerCreate, PartnerBootstrapOut
from app.services.internal_admin import require_internal_admin


router = APIRouter()

@router.post("/partners/bootstrap", response_model=PartnerBootstrapOut)
async def bootstrap_partner(payload: PartnerCreate, db: AsyncSession = Depends(get_db)) -> PartnerBootstrapOut:
    """
    Phase 0 bootstrap endpoint.
    In production, this would be internal-only (ops/admin) and protected by OIDC.
    """
    # Internal-only: we mark audit with "internal"
    tenant = Tenant(name=payload.tenant_name, created_by="internal", updated_by="internal")
    partner = Partner(tenant_id=tenant.id, name=payload.partner_name, created_by="internal", updated_by="internal")

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

    db.add(tenant)
    db.add(partner)
    db.add(key_row)
    await db.commit()

    return PartnerBootstrapOut(
        tenant_id=tenant.id,
        partner_id=partner.id,
        partner_admin_api_key=admin_key.plain,
    )
