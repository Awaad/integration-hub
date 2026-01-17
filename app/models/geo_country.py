from app.core.ids import gen_id
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.models.base import Base

class GeoCountry(Base):
    __tablename__ = "geo_countries"
    __table_args__ = (UniqueConstraint("code", name="uq_geo_country_code"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("gct"))
    code: Mapped[str] = mapped_column(String(8), nullable=False)   # e.g., "NCY"
    name: Mapped[str] = mapped_column(String(120), nullable=False) # e.g., "North Cyprus"

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
