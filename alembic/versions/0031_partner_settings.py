from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0031_partner_settings"
down_revision = "0030_listing_media_norm_hash"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "partner_settings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("partner_id", sa.String(), nullable=False),

        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),

        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # Multi-tenant safe uniqueness:
    op.create_index(
        "uq_partner_settings_tenant_partner",
        "partner_settings",
        ["tenant_id", "partner_id"],
        unique=True,
    )

    # Useful lookup index:
    op.create_index(
        "ix_partner_settings_tenant_partner",
        "partner_settings",
        ["tenant_id", "partner_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_partner_settings_tenant_partner", table_name="partner_settings")
    op.drop_index("uq_partner_settings_tenant_partner", table_name="partner_settings")
    op.drop_table("partner_settings")