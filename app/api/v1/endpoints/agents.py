from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import generate_api_key
from app.models.agent import Agent
from app.models.api_key import ApiKey
from app.schemas.agent import AgentCreate, AgentOut, AgentUpdate, ApiKeyCreated
from app.services.auth import Actor, require_partner_admin

router = APIRouter()

@router.post("/partners/{partner_id}/agents", response_model=AgentOut)
async def create_agent(
    partner_id: str,
    payload: AgentCreate,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
) -> AgentOut:
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    agent = Agent(
        tenant_id=actor.tenant_id,
        partner_id=partner_id,
        email=str(payload.email),
        display_name=payload.display_name,
        rules=payload.rules,
        created_by=actor.api_key_id,
        updated_by=actor.api_key_id,
    )
    db.add(agent)
    await db.commit()

    return AgentOut(
        id=agent.id,
        partner_id=agent.partner_id,
        email=agent.email,
        display_name=agent.display_name,
        is_active=agent.is_active,
        rules=agent.rules,
    )

@router.get("/partners/{partner_id}/agents", response_model=list[AgentOut])
async def list_agents(
    partner_id: str,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AgentOut]:
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    stmt = select(Agent).where(Agent.partner_id == partner_id, Agent.tenant_id == actor.tenant_id)
    agents = (await db.execute(stmt)).scalars().all()
    return [
        AgentOut(
            id=a.id,
            partner_id=a.partner_id,
            email=a.email,
            display_name=a.display_name,
            is_active=a.is_active,
            rules=a.rules,
        )
        for a in agents
    ]

@router.patch("/partners/{partner_id}/agents/{agent_id}", response_model=AgentOut)
async def update_agent(
    partner_id: str,
    agent_id: str,
    payload: AgentUpdate,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
) -> AgentOut:
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

    if payload.display_name is not None:
        agent.display_name = payload.display_name
    if payload.is_active is not None:
        agent.is_active = payload.is_active
    if payload.rules is not None:
        agent.rules = payload.rules
    if payload.updated_by is not None:
        agent.updated_by = actor.api_key_id

    await db.commit()

    return AgentOut(
        id=agent.id,
        partner_id=agent.partner_id,
        email=agent.email,
        display_name=agent.display_name,
        is_active=agent.is_active,
        rules=agent.rules,
    )

@router.post("/partners/{partner_id}/agents/{agent_id}/api-keys/rotate", response_model=ApiKeyCreated)
async def rotate_agent_api_key(
    partner_id: str,
    agent_id: str,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreated:
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    # Ensure agent exists
    stmt = select(Agent).where(Agent.id == agent_id, Agent.partner_id == partner_id, Agent.tenant_id == actor.tenant_id)
    agent = (await db.execute(stmt)).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Deactivate previous keys for that agent
    await db.execute(
        update(ApiKey)
        .where(
            ApiKey.tenant_id == actor.tenant_id,
            ApiKey.partner_id == partner_id,
            ApiKey.agent_id == agent_id,
            ApiKey.role == "agent",
            ApiKey.is_active.is_(True),
        )
        .values(is_active=False)
    )

    new_key = generate_api_key()
    row = ApiKey(
        tenant_id=actor.tenant_id,
        partner_id=partner_id,
        role="agent",
        agent_id=agent_id,
        key_prefix=new_key.prefix,
        key_hash=new_key.hashed,
        is_active=True,
        created_by=actor.api_key_id,
        updated_by=actor.api_key_id,
    )
    db.add(row)
    await db.commit()

    return ApiKeyCreated(
        id=row.id,
        plain_key=new_key.plain,
        key_prefix=new_key.prefix,
        role=row.role,
        agent_id=row.agent_id,
    )
