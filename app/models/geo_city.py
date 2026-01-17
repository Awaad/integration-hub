from app.core.ids import gen_id
from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.models.base import Base

class GeoCity(Base):
    __tablename__ = "geo_cities"
    __table_args__ = (
        UniqueConstraint("country_id", "slug", name="uq_geo_city_slug"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("gcy"))
    country_id: Mapped[str] = mapped_column(String, ForeignKey("geo_countries.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)  # normalized, e.g., "nicosia"

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
