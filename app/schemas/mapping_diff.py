from pydantic import BaseModel, Field

class MappingDiffResponse(BaseModel):
    destination: str
    checked: int
    exportable: int
    missing: dict = Field(default_factory=dict)  # grouped by category

class DestinationEnumDictImport(BaseModel):
    destination: str
    namespace: str
    mappings: dict[str, str] = Field(default_factory=dict)

class DestinationAreaDictImport(BaseModel):
    destination: str
    country_code: str
    # key: "city_slug:area_slug" value: destination_area_id
    mappings: dict[str, str] = Field(default_factory=dict)
