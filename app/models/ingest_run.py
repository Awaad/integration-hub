from app.core.ids import gen_id
from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.models.base import Base


class IngestRun(Base):
    """
    Immutable-ish record of an ingest request for diagnostics/support.

    We record both raw partner payload and the canonical payload (if mapping succeeds),
    plus validation/mapping errors.
    """
    __tablename__ = "ingest_runs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "partner_id",
            "partner_key",
            "source_listing_id",
            "idempotency_key",
            name="uq_ingest_run_idempotency",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("igr"))

    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), nullable=False)
    partner_id: Mapped[str] = mapped_column(String, ForeignKey("partners.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agents.id"), nullable=False)

    partner_key: Mapped[str] = mapped_column(String(80), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_listing_id: Mapped[str] = mapped_column(String(200), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)

    # Diagnostic payloads
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    canonical_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    status: Mapped[str] = mapped_column(String(40), nullable=False)  # "success" | "failed"

    listing_id: Mapped[str | None] = mapped_column(String, ForeignKey("listings.id"), nullable=True)

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
