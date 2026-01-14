from app.core.ids import gen_id
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, AuditMixin


class AgentExternalIdentity(AuditMixin, Base):
    __tablename__ = "agent_external_identities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "partner_id", "agent_id", "destination", name="uq_agent_dest_identity"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("aei"))
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), nullable=False)
    partner_id: Mapped[str] = mapped_column(String, ForeignKey("partners.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agents.id"), nullable=False)

    destination: Mapped[str] = mapped_column(String(120), nullable=False)
    external_agent_id: Mapped[str] = mapped_column(String(200), nullable=False)

    meta: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
