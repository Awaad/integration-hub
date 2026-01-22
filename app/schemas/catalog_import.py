from pydantic import BaseModel, Field

class EnumCatalogItem(BaseModel):
    source_key: str
    destination_value: str

class EnumCatalogImportRequest(BaseModel):
    source: str | None = None
    items: list[EnumCatalogItem] = Field(default_factory=list)

class GeoCatalogItem(BaseModel):
    city_slug: str
    area_slug: str
    destination_area_id: str

class GeoCatalogImportRequest(BaseModel):
    country_code: str
    source: str | None = None
    items: list[GeoCatalogItem] = Field(default_factory=list)

class CatalogImportResponse(BaseModel):
    run_id: str
    destination: str
    kind: str
    namespace: str | None = None
    country_code: str | None = None
    status: str
    summary: dict
