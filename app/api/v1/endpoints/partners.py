from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
import sqlalchemy as sa
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.core.db import get_db
from app.core.security import generate_api_key
from app.models.tenant import Tenant
from app.models.partner import Partner
from app.models.agent import Agent
from app.models.api_key import ApiKey
from app.schemas.partner import PartnerCreate, PartnerBootstrapOut, PartnerRotateKeyOut
from app.services.internal_admin import require_internal_admin
from app.services.auth import Actor, require_partner_admin
from app.models.agent_external_identity import AgentExternalIdentity
from app.schemas.agent_external_identity import (AgentExternalIdentityUpsert, AgentExternalIdentityOut,)
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
async def rotate_partner_admin_key(partner_id: str, db: AsyncSession = Depends(get_db)) -> PartnerRotateKeyOut:
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



@router.put(
    "/partners/{partner_id}/agents/{agent_id}/external-identities/{destination}",
    response_model=AgentExternalIdentityOut,
)
async def upsert_agent_external_identity(
    partner_id: str,
    agent_id: str,
    destination: str,
    payload: AgentExternalIdentityUpsert,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
) -> AgentExternalIdentityOut:
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    agent = (
        await db.execute(
            select(Agent).where(
                Agent.id == agent_id,
                Agent.partner_id == partner_id,
                Agent.tenant_id == actor.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    destination_norm = destination.lower().strip()
    stmt = (
        insert(AgentExternalIdentity)
        .values(
            tenant_id=actor.tenant_id,
            partner_id=partner_id,
            agent_id=agent_id,
            destination=destination_norm,
            external_agent_id=payload.external_agent_id,
            meta=payload.metadata,
            is_active=payload.is_active,
            created_by=actor.api_key_id,
            updated_by=actor.api_key_id,
        )
        .on_conflict_do_update(
            constraint="uq_agent_dest_identity",
            set_={
                "external_agent_id": payload.external_agent_id,
                "meta": payload.metadata,
                "is_active": payload.is_active,
                "updated_by": actor.api_key_id,
            },
        )
        .returning(AgentExternalIdentity)
    )

    try:
        row = (await db.execute(stmt)).scalar_one()
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Constraint violation")

    return AgentExternalIdentityOut(
        id=row.id,
        tenant_id=row.tenant_id,
        partner_id=row.partner_id,
        agent_id=row.agent_id,
        destination=row.destination,
        external_agent_id=row.external_agent_id,
        metadata=row.meta,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
        created_by=row.created_by,
        updated_by=row.updated_by,
    )


@router.get(
    "/partners/{partner_id}/agents/{agent_id}/external-identities",
    response_model=list[AgentExternalIdentityOut],
)
async def list_agent_external_identities(
    partner_id: str,
    agent_id: str,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AgentExternalIdentityOut]:
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    # Ensure agent exists within this tenant+partner
    stmt = select(Agent).where(
        Agent.id == agent_id,
        Agent.partner_id == partner_id,
        Agent.tenant_id == actor.tenant_id,
    )
    agent = (await db.execute(stmt)).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    rows = (
        await db.execute(
            select(AgentExternalIdentity)
            .where(
                AgentExternalIdentity.tenant_id == actor.tenant_id,
                AgentExternalIdentity.partner_id == partner_id,
                AgentExternalIdentity.agent_id == agent_id,
            )
            .order_by(AgentExternalIdentity.destination.asc())
        )
    ).scalars().all()

    return [
        AgentExternalIdentityOut(
            id=r.id,
            tenant_id=r.tenant_id,
            partner_id=r.partner_id,
            agent_id=r.agent_id,
            destination=r.destination,
            external_agent_id=r.external_agent_id,
            metadata=r.meta,
            is_active=r.is_active,
            created_at=r.created_at,
            updated_at=r.updated_at,
            created_by=r.created_by,
            updated_by=r.updated_by,
        )
        for r in rows
    ]