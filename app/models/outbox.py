import uuid
from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime, Integer

from app.models.base import Base


class OutboxEvent(Base):
    __tablename__ = "outbox"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"obx_{uuid.uuid4().hex}")

    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "listing"
    aggregate_id: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(200), nullable=False)      # e.g. "listing.upserted"

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")  # pending/sent/failed
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
