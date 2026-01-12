from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_json
from app.core.db import get_db
from app.models.agent import Agent
from app.models.agent_credential import AgentCredential
from app.schemas.credentials import AgentCredentialOut, AgentCredentialUpsert
from app.services.auth import Actor, require_partner_admin

router = APIRouter()


async def _assert_agent_access(db: AsyncSession, actor: Actor, partner_id: str, agent_id: str) -> None:
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    stmt = select(Agent).where(
        Agent.id == agent_id,
        Agent.partner_id == partner_id,
        Agent.tenant_id == actor.tenant_id,
    )
    agent = (await db.execute(stmt)).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")


@router.get(
    "/partners/{partner_id}/agents/{agent_id}/credentials",
    response_model=list[AgentCredentialOut],
)
async def list_agent_credentials(
    partner_id: str,
    agent_id: str,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AgentCredentialOut]:
    await _assert_agent_access(db, actor, partner_id, agent_id)

    stmt = select(AgentCredential).where(
        AgentCredential.tenant_id == actor.tenant_id,
        AgentCredential.partner_id == partner_id,
        AgentCredential.agent_id == agent_id,
    ).order_by(AgentCredential.destination.asc())

    rows = (await db.execute(stmt)).scalars().all()
    return [
        AgentCredentialOut(
            id=r.id,
            agent_id=r.agent_id,
            destination=r.destination,
            auth_type=r.auth_type,
            metadata=r.meta,
            is_active=r.is_active,
            created_at=str(r.created_at),
            updated_at=str(r.updated_at),
            created_by=r.created_by,
            updated_by=r.updated_by,
        )
        for r in rows
    ]


@router.put(
    "/partners/{partner_id}/agents/{agent_id}/credentials/{destination}",
    response_model=AgentCredentialOut,
)
async def upsert_agent_credential(
    partner_id: str,
    agent_id: str,
    destination: str,
    payload: AgentCredentialUpsert,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
) -> AgentCredentialOut:
    await _assert_agent_access(db, actor, partner_id, agent_id)

    # Ensure path destination matches body destination if provided
    if payload.destination and payload.destination != destination:
        raise HTTPException(status_code=422, detail="destination mismatch")

    # Encrypt secrets (never returned)
    ciphertext = encrypt_json(payload.secrets)

    stmt = select(AgentCredential).where(
        AgentCredential.tenant_id == actor.tenant_id,
        AgentCredential.partner_id == partner_id,
        AgentCredential.agent_id == agent_id,
        AgentCredential.destination == destination,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()

    if row:
        row.auth_type = payload.auth_type
        row.secret_ciphertext = ciphertext
        row.meta = payload.metadata
        row.is_active = payload.is_active
        row.updated_by = actor.api_key_id
    else:
        row = AgentCredential(
            tenant_id=actor.tenant_id,
            partner_id=partner_id,
            agent_id=agent_id,
            destination=destination,
            auth_type=payload.auth_type,
            secret_ciphertext=ciphertext,
            meta=payload.metadata,
            is_active=payload.is_active,
            created_by=actor.api_key_id,
            updated_by=actor.api_key_id,
        )
        db.add(row)

    await db.commit()
    await db.refresh(row)

    return AgentCredentialOut(
        id=row.id,
        agent_id=row.agent_id,
        destination=row.destination,
        auth_type=row.auth_type,
        metadata=row.meta,
        is_active=row.is_active,
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
        created_by=row.created_by,
        updated_by=row.updated_by,
    )


@router.delete("/partners/{partner_id}/agents/{agent_id}/credentials/{destination}")
async def delete_agent_credential(
    partner_id: str,
    agent_id: str,
    destination: str,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _assert_agent_access(db, actor, partner_id, agent_id)

    res = await db.execute(
        delete(AgentCredential).where(
            AgentCredential.tenant_id == actor.tenant_id,
            AgentCredential.partner_id == partner_id,
            AgentCredential.agent_id == agent_id,
            AgentCredential.destination == destination,
        )
    )
    await db.commit()

    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Credential not found")

    return {"status": "deleted"}
