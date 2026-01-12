from pydantic import BaseModel, Field


class AgentCredentialUpsert(BaseModel):
    destination: str = Field(min_length=1, max_length=120)
    auth_type: str = Field(min_length=1, max_length=40)

    # Secrets to encrypt and store (never returned)
    secrets: dict = Field(default_factory=dict)

    # Non-secret, safe to show on dashboards
    metadata: dict = Field(default_factory=dict)

    is_active: bool = True


class AgentCredentialOut(BaseModel):
    id: str
    agent_id: str
    destination: str
    auth_type: str
    metadata: dict
    is_active: bool
    created_at: str
    updated_at: str
    created_by: str | None
    updated_by: str | None
