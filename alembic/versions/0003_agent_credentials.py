from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_agent_credentials"
down_revision = "0002_add_audit_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_credentials",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("partner_id", sa.String(), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("destination", sa.String(length=120), nullable=False),
        sa.Column("auth_type", sa.String(length=40), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),

        sa.UniqueConstraint("tenant_id", "partner_id", "agent_id", "destination", name="uq_agent_dest_cred"),
    )

    op.create_index("ix_agent_credentials_agent_dest", "agent_credentials", ["agent_id", "destination"])
    op.create_index("ix_agent_credentials_partner", "agent_credentials", ["partner_id"])


def downgrade():
    op.drop_index("ix_agent_credentials_partner", table_name="agent_credentials")
    op.drop_index("ix_agent_credentials_agent_dest", table_name="agent_credentials")
    op.drop_table("agent_credentials")
