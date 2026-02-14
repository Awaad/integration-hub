from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime
from sqlalchemy.sql import func

from app.models.base import Base


class PartnerSettings(Base):
    __tablename__ = "partner_settings"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "partner_id",
            name="uq_partner_settings_tenant_partner",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)

    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    partner_id: Mapped[str] = mapped_column(String, nullable=False)

    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )