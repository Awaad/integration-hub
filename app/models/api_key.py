import uuid
from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.models.base import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"key_{uuid.uuid4().hex}")
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), nullable=False)
    partner_id: Mapped[str] = mapped_column(String, ForeignKey("partners.id"), nullable=False)

    # Role: "partner_admin" can manage agents; "agent" can manage their own listings.
    role: Mapped[str] = mapped_column(String(50), nullable=False)

    agent_id: Mapped[str | None] = mapped_column(String, ForeignKey("agents.id"), nullable=True)

    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    rotated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
