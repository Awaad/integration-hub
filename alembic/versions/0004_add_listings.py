from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_add_listings"
down_revision = "0003_agent_credentials"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "listings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("partner_id", sa.String(), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id"), nullable=False),

        sa.Column("source_listing_id", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),

        sa.Column("schema", sa.String(length=80), nullable=False, server_default="canonical.listing.v1"),
        sa.Column("schema_version", sa.String(length=20), nullable=False, server_default="1.0.0"),

        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("content_hash", sa.String(length=80), nullable=False),

        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),

        sa.UniqueConstraint("tenant_id", "partner_id", "agent_id", "source_listing_id", name="uq_listing_source_id_per_agent"),
    )

    op.create_index("ix_listings_partner_agent", "listings", ["partner_id", "agent_id"])
    op.create_index("ix_listings_updated_at", "listings", ["updated_at"])


def downgrade():
    op.drop_index("ix_listings_updated_at", table_name="listings")
    op.drop_index("ix_listings_partner_agent", table_name="listings")
    op.drop_table("listings")
