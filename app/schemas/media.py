from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl


class MediaIngestUrlIn(BaseModel):
    url: HttpUrl
    type: str = Field(default="image", max_length=32)
    order_index: int = Field(default=0, ge=0)
    caption: str | None = None
    is_primary: bool = False


class MediaObjectOut(BaseModel):
    id: str
    tenant_id: str
    partner_id: str
    agent_id: str

    content_hash: str
    byte_size: int
    mime_type: str

    storage_backend: str
    storage_key: str

    source_url: str | None = None
    width: int | None = None
    height: int | None = None

    created_by: str | None = None
    updated_by: str | None = None


class ListingMediaOut(BaseModel):
    id: str
    tenant_id: str
    partner_id: str
    agent_id: str

    listing_id: str
    media_id: str

    type: str
    order_index: int
    caption: str | None = None
    is_primary: bool

    created_by: str | None = None  
    updated_by: str | None = None


class MediaIngestUrlOut(BaseModel):
    media: MediaObjectOut
    link: ListingMediaOut
