from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_add_idempotency_keys"
down_revision = "0004_add_listings"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("partner_id", sa.String(), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("actor_api_key_id", sa.String(), sa.ForeignKey("api_keys.id"), nullable=False),

        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=80), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "key", name="uq_idempotency_tenant_key"),
    )
    op.create_index("ix_idempotency_keys_tenant_created", "idempotency_keys", ["tenant_id", "created_at"])


def downgrade():
    op.drop_index("ix_idempotency_keys_tenant_created", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
