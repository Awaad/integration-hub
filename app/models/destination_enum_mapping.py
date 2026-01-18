from app.core.ids import gen_id
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.models.base import Base, AuditMixin


class DestinationEnumMapping(AuditMixin, Base):
    """
    Generic mapping table for destination enum ids.
    Examples:
      destination=101evler, namespace=property_type, source_key=apartment, destination_value=123
      destination=101evler, namespace=currency, source_key=EUR, destination_value=601
      destination=101evler, namespace=rooms, source_key=3, destination_value=77
    """
    __tablename__ = "destination_enum_mappings"
    __table_args__ = (
        UniqueConstraint("destination", "namespace", "source_key", name="uq_dest_enum_map"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("dem"))

    destination: Mapped[str] = mapped_column(String(120), nullable=False)
    namespace: Mapped[str] = mapped_column(String(80), nullable=False)      # e.g. "property_type", "currency", "rooms"
    source_key: Mapped[str] = mapped_column(String(180), nullable=False)    # canonical key
    destination_value: Mapped[str] = mapped_column(String(64), nullable=False)  # destination enum id

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
