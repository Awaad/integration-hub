from __future__ import annotations

from app.core.ids import gen_id
from sqlalchemy import String, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base

class DestinationCatalogImportItem(Base):
    __tablename__ = "destination_catalog_import_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("dci"))
    run_id: Mapped[str] = mapped_column(String, ForeignKey("destination_catalog_import_runs.id", ondelete="CASCADE"), nullable=False)

    key: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    existing_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # insert|update|noop|invalid
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
