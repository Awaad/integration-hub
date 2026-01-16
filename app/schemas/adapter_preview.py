from pydantic import BaseModel, Field
from typing import Any


class AdapterPreviewRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    source_listing_id: str | None = None
    agent_id: str | None = None
    adapter_version: str | None = None


class AdapterPreviewResponse(BaseModel):
    ok: bool
    partner_key: str
    canonical_schema: str
    canonical_schema_version: str
    canonical: dict[str, Any] | None
    normalized: dict[str, Any] | None
    content_hash: str | None
    adapter_version: str | None = None
    errors: list[dict[str, Any]]

