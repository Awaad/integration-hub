import uuid
from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import gen_id

from app.models.base import Base, AuditMixin


class Listing(AuditMixin, Base):
    __tablename__ = "listings"
    __table_args__ = (
        # each agent can have stable external IDs within their scope
        UniqueConstraint(
            "tenant_id", "partner_id", "agent_id", "source_listing_id",
            name="uq_listing_source_id_per_agent"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("lst"))

    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), nullable=False)
    partner_id: Mapped[str] = mapped_column(String, ForeignKey("partners.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agents.id"), nullable=False)

    # Partner/agent system stable ID for the listing
    source_listing_id: Mapped[str] = mapped_column(String(120), nullable=False)

    # "draft" | "published" | "archived"
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")

    # Canonical schema identifier/version (helps future migrations)
    schema: Mapped[str] = mapped_column(String(80), nullable=False, default="canonical.listing.v1")
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")

    # Canonical-ish payload snapshot  flexible
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # hash of payload for change detection
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
