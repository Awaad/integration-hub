from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_deliveries"
down_revision = "0007_outbox_processing_fields"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "deliveries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("partner_id", sa.String(), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("listing_id", sa.String(), sa.ForeignKey("listings.id"), nullable=False),
        sa.Column("destination", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "destination", "listing_id", name="uq_delivery_dest_listing"),
    )
    op.create_index("ix_deliveries_listing", "deliveries", ["listing_id"])
    op.create_index("ix_deliveries_dest_status", "deliveries", ["destination", "status"])

    op.create_table(
        "delivery_attempts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("delivery_id", sa.String(), sa.ForeignKey("deliveries.id"), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("request", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_delivery_attempts_delivery", "delivery_attempts", ["delivery_id"])

def downgrade():
    op.drop_index("ix_delivery_attempts_delivery", table_name="delivery_attempts")
    op.drop_table("delivery_attempts")
    op.drop_index("ix_deliveries_dest_status", table_name="deliveries")
    op.drop_index("ix_deliveries_listing", table_name="deliveries")
    op.drop_table("deliveries")
