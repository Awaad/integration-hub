from __future__ import annotations
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.ids import gen_id
from app.models.base import Base


class MediaVariant(Base):
    __tablename__ = "media_variants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("mvr"))

    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    partner_id: Mapped[str] = mapped_column(String, nullable=False)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False)

    media_id: Mapped[str] = mapped_column(String, ForeignKey("media_objects.id", ondelete="CASCADE"), nullable=False)
    variant: Mapped[str] = mapped_column(String(32), nullable=False)

    variant_hash: Mapped[str] = mapped_column(String(64), nullable=False)  

    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)

    storage_backend: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(400), nullable=False)

    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
