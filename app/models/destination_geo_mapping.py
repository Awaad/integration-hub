from app.core.ids import gen_id
from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.models.base import Base, AuditMixin

class DestinationGeoMapping(AuditMixin, Base):
    """
    Maps shared Geo entities to destination-specific IDs.
    Example: North Cyprus -> 101evler area_id values.
    """
    __tablename__ = "destination_geo_mappings"
    __table_args__ = (
        UniqueConstraint("destination", "geo_area_id", name="uq_dest_geo_area"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("dgm"))
    destination: Mapped[str] = mapped_column(String(120), nullable=False)

    geo_country_id: Mapped[str | None] = mapped_column(String, ForeignKey("geo_countries.id"), nullable=True)
    geo_city_id: Mapped[str | None] = mapped_column(String, ForeignKey("geo_cities.id"), nullable=True)
    geo_area_id: Mapped[str | None] = mapped_column(String, ForeignKey("geo_areas.id"), nullable=True)

    destination_city_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    destination_area_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
