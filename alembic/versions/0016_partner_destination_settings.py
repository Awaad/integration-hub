from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0016_partner_destination_setting"
down_revision = "0015_ingest_runs_adapter_version" 
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "partner_destination_settings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("partner_id", sa.String(), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("destination", sa.String(length=120), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.UniqueConstraint("tenant_id", "partner_id", "destination", name="uq_partner_destination"),
    )
    op.create_index("ix_partner_dest_partner", "partner_destination_settings", ["partner_id"])
    op.create_index("ix_partner_dest_destination", "partner_destination_settings", ["destination"])


def downgrade():
    op.drop_index("ix_partner_dest_destination", table_name="partner_destination_settings")
    op.drop_index("ix_partner_dest_partner", table_name="partner_destination_settings")
    op.drop_table("partner_destination_settings")
