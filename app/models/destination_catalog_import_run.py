from __future__ import annotations
from datetime import datetime
from app.core.ids import gen_id
from sqlalchemy import String, DateTime, JSON, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base

class DestinationCatalogImportRun(Base):
    __tablename__ = "destination_catalog_import_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("dcr"))
    destination: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # enum|geo
    namespace: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # previewed|applied|failed
    summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    catalog_set_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("destination_catalog_sets.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False,)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,)
