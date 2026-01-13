from pydantic import BaseModel, Field


class ListingUpsert(BaseModel):
    status: str = Field(default="draft", max_length=30)
    payload: dict = Field(default_factory=dict)

    # optional override for future
    schema: str = "canonical.listing.v1"
    schema_version: str = "1.0.0"


class ListingOut(BaseModel):
    id: str
    tenant_id: str
    partner_id: str
    agent_id: str
    source_listing_id: str
    status: str
    schema: str
    schema_version: str
    content_hash: str
    payload: dict
    created_by: str | None
    updated_by: str | None
