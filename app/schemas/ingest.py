from pydantic import BaseModel, Field
from typing import Any

class IngestListingRequest(BaseModel):
    # Partner payload (their schema)
    payload: dict[str, Any] = Field(default_factory=dict)

    # When using a partner_admin API key, they can specify which agent owns it.
    # When using an agent API key, this must be omitted (we infer agent_id).
    agent_id: str | None = None

class IngestListingResponse(BaseModel):
    listing_id: str
    source_listing_id: str
    schema: str
    schema_version: str
    content_hash: str
    material_change: bool
