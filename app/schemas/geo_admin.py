from pydantic import BaseModel, Field

class GeoCountryUpsert(BaseModel):
    code: str = Field(..., min_length=2, max_length=8)
    name: str = Field(..., min_length=2, max_length=120)

class GeoCityUpsert(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    slug: str = Field(..., min_length=1, max_length=120)

class GeoAreaUpsert(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    slug: str = Field(..., min_length=1, max_length=160)

class GeoBulkImportCities(BaseModel):
    country_code: str
    cities: list[GeoCityUpsert] = Field(default_factory=list)

class GeoBulkImportAreas(BaseModel):
    country_code: str
    city_slug: str
    areas: list[GeoAreaUpsert] = Field(default_factory=list)

class DestinationGeoAreaMappingUpsert(BaseModel):
    destination: str
    country_code: str
    city_slug: str
    area_slug: str
    destination_area_id: str = Field(..., min_length=1, max_length=64)
    destination_city_id: str | None = Field(default=None, max_length=64)
