import uuid
from app.core.ids import gen_id
from sqlalchemy import String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.models.base import Base, AuditMixin


class PartnerDestinationSetting(AuditMixin, Base):
    """
    Partner-level configuration per destination.
    Controls whether deliveries may be created for that destination.
    """
    __tablename__ = "partner_destination_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "partner_id", "destination", name="uq_partner_destination"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("pds"))
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), nullable=False)
    partner_id: Mapped[str] = mapped_column(String, ForeignKey("partners.id"), nullable=False)

    destination: Mapped[str] = mapped_column(String(120), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # arbitrary destination settings: feed config, rate limits, endpoints, etc.
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
