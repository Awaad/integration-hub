from app.core.ids import gen_id
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ListingExternalMapping(Base):
    __tablename__ = "listing_external_mappings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "destination", "listing_id", name="uq_listing_dest_mapping"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("lem"))
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), nullable=False)
    partner_id: Mapped[str] = mapped_column(String, ForeignKey("partners.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agents.id"), nullable=False)
    listing_id: Mapped[str] = mapped_column(String, ForeignKey("listings.id"), nullable=False)

    destination: Mapped[str] = mapped_column(String(120), nullable=False)
    external_listing_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    last_synced_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    meta: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
