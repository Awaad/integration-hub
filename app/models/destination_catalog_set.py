from __future__ import annotations
import uuid
from app.core.ids import gen_id
from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base

class DestinationCatalogSet(Base):
    __tablename__ = "destination_catalog_sets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("dcs"))
    destination: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False)  # draft|pending|active|rejected|archived
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    approved_at: Mapped = mapped_column(DateTime(timezone=True), nullable=True)
