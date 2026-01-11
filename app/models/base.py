from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime


class Base(DeclarativeBase):
    pass

class AuditMixin:
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # ApiKey.id that created/updated the record (or "internal")
    created_by: Mapped[str | None] = mapped_column(nullable=True)
    updated_by: Mapped[str | None] = mapped_column(nullable=True)