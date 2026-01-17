from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0017_feed_snapshots"
down_revision = "0016_partner_destination_setting"  
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "feed_snapshots",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("partner_id", sa.String(), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("destination", sa.String(length=120), nullable=False),
        sa.Column("storage_uri", sa.String(length=500), nullable=False),
        sa.Column("format", sa.String(length=40), nullable=False),
        sa.Column("content_hash", sa.String(length=80), nullable=False),
        sa.Column("listing_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
    )
    op.create_index("ix_feed_snapshots_partner_dest", "feed_snapshots", ["partner_id", "destination"])
    op.create_index("ix_feed_snapshots_created_at", "feed_snapshots", ["created_at"])

def downgrade():
    op.drop_index("ix_feed_snapshots_created_at", table_name="feed_snapshots")
    op.drop_index("ix_feed_snapshots_partner_dest", table_name="feed_snapshots")
    op.drop_table("feed_snapshots")
