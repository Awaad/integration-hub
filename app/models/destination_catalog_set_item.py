from __future__ import annotations
import datetime
import uuid
from sqlalchemy import String, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base

class DestinationCatalogSetItem(Base):
    __tablename__ = "destination_catalog_set_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"dcsi_{uuid.uuid4().hex}")
    catalog_set_id: Mapped[str] = mapped_column(String, ForeignKey("destination_catalog_sets.id", ondelete="CASCADE"), nullable=False)

    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # enum|geo

    namespace: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    destination_value: Mapped[str | None] = mapped_column(String(200), nullable=True)

    geo_key: Mapped[str | None] = mapped_column(String(200), nullable=True)  # city:area
    geo_country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    destination_area_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
