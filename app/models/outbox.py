from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime, Integer

from app.core.ids import gen_id
from app.models.base import Base, AuditMixin


class OutboxEvent(AuditMixin, Base):
    __tablename__ = "outbox"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("obx"))

    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "listing"
    aggregate_id: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(200), nullable=False)      # e.g. "listing.upserted"

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")  # pending/sent/failed
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    dedupe_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lease_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime| None] = mapped_column(DateTime(timezone=True), nullable=True)
