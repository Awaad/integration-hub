import uuid
from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, AuditMixin


class AgentCredential(AuditMixin, Base):
    __tablename__ = "agent_credentials"
    __table_args__ = (
        UniqueConstraint("tenant_id", "partner_id", "agent_id", "destination", name="uq_agent_dest_cred"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"crd_{uuid.uuid4().hex}")

    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), nullable=False)
    partner_id: Mapped[str] = mapped_column(String, ForeignKey("partners.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agents.id"), nullable=False)

    # Destination key, e.g. "mls_hangiev", "mls_realtor", "website_wp", "website_1"
    destination: Mapped[str] = mapped_column(String(120), nullable=False)

    # "api_key" | "basic" | "oauth2_client" | "token" | "custom"
    auth_type: Mapped[str] = mapped_column(String(40), nullable=False)

    # Encrypted JSON blob of secrets (never returned by API)
    secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)

    # Non-secret metadata shown in dashboard (labels, endpoints, notes)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
