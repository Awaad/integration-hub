from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class AgentExternalIdentityUpsert(BaseModel):
    destination: str = Field(min_length=1, max_length=120)
    external_agent_id: str = Field(..., max_length=200)
    metadata: dict = Field(default_factory=dict)
    is_active: bool = True


class AgentExternalIdentityOut(BaseModel):
    id: str
    tenant_id: str
    partner_id: str
    agent_id: str

    destination: str
    external_agent_id: str
    metadata: dict
    is_active: bool

    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    updated_by: str | None = None
