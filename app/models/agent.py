from app.core.ids import gen_id
from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, AuditMixin


class Agent(AuditMixin, Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("agt"))
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), nullable=False)
    partner_id: Mapped[str] = mapped_column(String, ForeignKey("partners.id"), nullable=False)

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Rules are controlled by partner admins:
    # e.g. allowed destinations, field ownership, listing limits, etc.
    rules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    partner = relationship("Partner", lazy="joined")
