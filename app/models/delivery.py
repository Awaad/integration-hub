from app.core.ids import gen_id
from sqlalchemy import ForeignKey, String, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.models.base import Base


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "destination", "listing_id", name="uq_delivery_dest_listing"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("dly"))
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), nullable=False)
    partner_id: Mapped[str] = mapped_column(String, ForeignKey("partners.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agents.id"), nullable=False)

    listing_id: Mapped[str] = mapped_column(String, ForeignKey("listings.id"), nullable=False)
    destination: Mapped[str] = mapped_column(String(120), nullable=False)  # e.g. "mls_a", "website"

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")  # pending/success/failed
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    last_attempt_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)

    next_retry_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retryable: Mapped[bool] = mapped_column(nullable=False, default=True)
    
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("att"))
    delivery_id: Mapped[str] = mapped_column(String, ForeignKey("deliveries.id"), nullable=False)

    status: Mapped[str] = mapped_column(String(30), nullable=False)  # success/failed
    request: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # projection/meta (no secrets)
    response: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    dead_lettered_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)