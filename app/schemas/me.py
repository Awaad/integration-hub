from pydantic import BaseModel


class MeOut(BaseModel):
    api_key_id: str
    tenant_id: str
    partner_id: str
    role: str
    agent_id: str | None
