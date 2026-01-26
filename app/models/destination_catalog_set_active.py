from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base

class DestinationCatalogSetActive(Base):
    __tablename__ = "destination_catalog_set_active"

    destination: Mapped[str] = mapped_column(String(64), primary_key=True)
    country_code: Mapped[str | None] = mapped_column(String(8), primary_key=True, nullable=False, default="", server_default="")
    active_catalog_set_id: Mapped[str] = mapped_column(String, ForeignKey("destination_catalog_sets.id", ondelete="RESTRICT"), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
