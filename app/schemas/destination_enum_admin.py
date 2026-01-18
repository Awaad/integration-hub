from pydantic import BaseModel, Field

class DestinationEnumUpsert(BaseModel):
    destination: str
    namespace: str
    source_key: str
    destination_value: str = Field(..., min_length=1, max_length=64)

class DestinationEnumBulkUpsert(BaseModel):
    destination: str
    namespace: str
    items: list[DestinationEnumUpsert]
