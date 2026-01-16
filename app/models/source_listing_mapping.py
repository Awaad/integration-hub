from app.core.ids import gen_id
from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.models.base import Base


class SourceListingMapping(Base):
    """
    Maps (partner_key, source_listing_id) -> hub listing_id.

    This allows partners to keep their own identifiers while Hub maintains a stable canonical listing id.
    """
    __tablename__ = "source_listing_mappings"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "partner_id",
            "partner_key",
            "source_listing_id",
            name="uq_source_listing_mapping",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("slm"))
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), nullable=False)
    partner_id: Mapped[str] = mapped_column(String, ForeignKey("partners.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agents.id"), nullable=False)

    partner_key: Mapped[str] = mapped_column(String(80), nullable=False)
    source_listing_id: Mapped[str] = mapped_column(String(200), nullable=False)

    listing_id: Mapped[str] = mapped_column(String, ForeignKey("listings.id"), nullable=False)

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
