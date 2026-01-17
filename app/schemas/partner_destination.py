from pydantic import BaseModel, Field

class PartnerDestinationUpsert(BaseModel):
    is_enabled: bool = False
    config: dict = Field(default_factory=dict)

class PartnerDestinationOut(BaseModel):
    destination: str
    is_enabled: bool
    config: dict
    created_by: str | None
    updated_by: str | None
