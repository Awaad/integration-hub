import uuid
from app.core.ids import gen_id
from sqlalchemy import String, JSON, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("aud"))
    tenant_id: Mapped[str | None] = mapped_column(String, nullable=True)
    partner_id: Mapped[str | None] = mapped_column(String, nullable=True)

    actor_api_key_id: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)

    target_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
