from __future__ import annotations
from datetime import datetime
from app.core.ids import gen_id
from sqlalchemy import String, DateTime, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import AuditMixin, Base

class PartnerPublicToken(AuditMixin, Base):
    __tablename__ = "partner_public_tokens"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("ppt"))
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    partner_id: Mapped[str] = mapped_column(String, nullable=False)

    scope: Mapped[str] = mapped_column(String(32), nullable=False)  # "media"
    token_prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    