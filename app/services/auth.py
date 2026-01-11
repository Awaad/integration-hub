from dataclasses import dataclass
from fastapi import Depends, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import hash_api_key
from app.models.api_key import ApiKey

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass(frozen=True)
class Actor:
    api_key_id: str
    tenant_id: str
    partner_id: str
    role: str  # "partner_admin" | "agent"
    agent_id: str | None


async def get_actor(
    api_key: str | None = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> Actor:
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key")

    hashed = hash_api_key(api_key)
    stmt = select(ApiKey).where(ApiKey.key_hash == hashed, ApiKey.is_active.is_(True))
    row = (await db.execute(stmt)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return Actor(
        api_key_id=row.id,
        tenant_id=row.tenant_id,
        partner_id=row.partner_id,
        role=row.role,
        agent_id=row.agent_id,
    )


def require_partner_admin(actor: Actor = Depends(get_actor)) -> Actor:
    if actor.role != "partner_admin":
        raise HTTPException(status_code=403, detail="Partner admin role required")
    return actor


def require_agent(actor: Actor = Depends(get_actor)) -> Actor:
    if actor.role != "agent":
        raise HTTPException(status_code=403, detail="Agent role required")
    if not actor.agent_id:
        raise HTTPException(status_code=403, detail="Agent id missing")
    return actor
