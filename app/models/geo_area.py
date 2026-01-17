from app.core.ids import gen_id
from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.models.base import Base

class GeoArea(Base):
    __tablename__ = "geo_areas"
    __table_args__ = (
        UniqueConstraint("city_id", "slug", name="uq_geo_area_slug"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("gar"))
    city_id: Mapped[str] = mapped_column(String, ForeignKey("geo_cities.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)  # normalized, e.g., "dereboyu"

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
