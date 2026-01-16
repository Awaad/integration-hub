from alembic import op
import sqlalchemy as sa

revision = "0013_source_listing_mappings"
down_revision = "0012_delivery_retry_schedule" 
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_listing_mappings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("partner_id", sa.String(), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("partner_key", sa.String(length=80), nullable=False),
        sa.Column("source_listing_id", sa.String(length=200), nullable=False),
        sa.Column("listing_id", sa.String(), sa.ForeignKey("listings.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "partner_id", "partner_key", "source_listing_id", name="uq_source_listing_mapping"),
    )
    op.create_index("ix_slm_partner_key_source", "source_listing_mappings", ["partner_key", "source_listing_id"])
    op.create_index("ix_slm_listing_id", "source_listing_mappings", ["listing_id"])


def downgrade():
    op.drop_index("ix_slm_listing_id", table_name="source_listing_mappings")
    op.drop_index("ix_slm_partner_key_source", table_name="source_listing_mappings")
    op.drop_table("source_listing_mappings")
