from app.core.ids import gen_id
from sqlalchemy import String, ForeignKey, Text, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.models.base import Base, AuditMixin


class FeedSnapshot(AuditMixin, Base):
    """
    Represents a generated hosted feed file for a destination and partner.
    """
    __tablename__ = "feed_snapshots"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("fds"))

    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), nullable=False)
    partner_id: Mapped[str] = mapped_column(String, ForeignKey("partners.id"), nullable=False)

    destination: Mapped[str] = mapped_column(String(120), nullable=False)

    # Where the file lives. For now: local path. Later: s3://bucket/key
    storage_uri: Mapped[str] = mapped_column(String(500), nullable=False)

    # Content metadata
    format: Mapped[str] = mapped_column(String(40), nullable=False)  # "xml" | "csv" | "json"
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    listing_count: Mapped[int] = mapped_column(nullable=False, default=0)

    # extra metadata (generator version, warnings, etc.)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # gzip 
    gzip_storage_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    gzip_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
