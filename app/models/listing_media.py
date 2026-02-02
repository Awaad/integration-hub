from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import gen_id
from app.models.base import Base
from app.models.base import AuditMixin  


class ListingMedia(AuditMixin, Base):
    __tablename__ = "listing_media"
    __table_args__ = (
        Index("ix_listing_media_listing", "listing_id"),
        Index("ix_listing_media_owner", "tenant_id", "partner_id", "agent_id", "listing_id"),
        Index("ix_listing_media_listing_order", "listing_id", "order_index", "created_at"),
        Index(
            "uq_listing_media_primary_per_listing",
            "listing_id",
            unique=True,
            postgresql_where=text("is_primary = true"),
        ),
        Index("uq_listing_media_listing_media", "tenant_id", "partner_id", "agent_id", "listing_id", "media_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("lmd"))

    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    partner_id: Mapped[str] = mapped_column(String, nullable=False)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False,)

    listing_id: Mapped[str] = mapped_column(String, ForeignKey("listings.id", ondelete="CASCADE"), nullable=False,)
    media_id: Mapped[str] = mapped_column(String, ForeignKey("media_objects.id", ondelete="CASCADE"), nullable=False,)

    type: Mapped[str] = mapped_column(String(32), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
