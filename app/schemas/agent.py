from pydantic import BaseModel, EmailStr, Field


class AgentCreate(BaseModel):
    email: EmailStr
    display_name: str
    rules: dict = Field(default_factory=dict)


class AgentUpdate(BaseModel):
    display_name: str | None = None
    is_active: bool | None = None
    rules: dict | None = None


class AgentOut(BaseModel):
    id: str
    partner_id: str
    email: EmailStr
    display_name: str
    is_active: bool
    rules: dict


class ApiKeyOut(BaseModel):
    id: str
    key_prefix: str
    role: str
    agent_id: str | None
    is_active: bool


class ApiKeyCreated(BaseModel):
    id: str
    plain_key: str  # returned only once
    key_prefix: str
    role: str
    agent_id: str | None
