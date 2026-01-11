import uuid
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, AuditMixin


class Partner(AuditMixin, Base):
    __tablename__ = "partners"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"prt_{uuid.uuid4().hex}")
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    tenant = relationship("Tenant", lazy="joined")
