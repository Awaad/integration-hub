from __future__ import annotations

from sqlalchemy import ForeignKey, CheckConstraint, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import gen_id
from app.models.base import Base
from app.models.base import AuditMixin  


class MediaObject(AuditMixin, Base):
    __tablename__ = "media_objects"
    __table_args__ = (
        CheckConstraint("byte_size > 0", name="ck_media_objects_byte_size_positive"),
        Index("ix_media_objects_tenant_created", "tenant_id", "created_at"),
        Index("ix_media_objects_owner_created", "tenant_id", "partner_id", "agent_id", "created_at"),
        Index(
            "uq_media_objects_owner_hash",
            "tenant_id",
            "partner_id",
            "agent_id",
            "content_hash",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("med"))

    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    partner_id: Mapped[str] = mapped_column(String, nullable=False)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False)

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)

    storage_backend: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(400), nullable=False)

    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
