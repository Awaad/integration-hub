from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_external_identities"
down_revision = "0010_delivery_retry_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_external_identities",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("partner_id", sa.String(), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("destination", sa.String(length=120), nullable=False),
        sa.Column("external_agent_id", sa.String(length=200), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.UniqueConstraint(
            "tenant_id",
            "partner_id",
            "agent_id",
            "destination",
            name="uq_agent_dest_identity",
        ),
    )
    op.create_index(
        "ix_agent_external_identities_tenant_destination",
        "agent_external_identities",
        ["tenant_id", "destination"],
    )
    op.create_index(
        "ix_agent_external_identities_agent_id",
        "agent_external_identities",
        ["agent_id"],
    )
    op.create_index(
        "ix_agent_external_identities_partner_id",
        "agent_external_identities",
        ["partner_id"],
    )
    op.create_index(
        "ix_agent_external_identities_dest_external_agent",
        "agent_external_identities",
        ["destination", "external_agent_id"],
    )

    op.create_table(
        "listing_external_mappings",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("partner_id", sa.String(), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("listing_id", sa.String(), sa.ForeignKey("listings.id"), nullable=False),
        sa.Column("destination", sa.String(length=120), nullable=False),
        sa.Column("external_listing_id", sa.String(length=200), nullable=True),
        sa.Column("last_synced_hash", sa.String(length=80), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "destination",
            "listing_id",
            name="uq_listing_dest_mapping",
        ),
    )

    op.create_index(
        "ix_listing_external_mappings_listing_id",
        "listing_external_mappings",
        ["listing_id"],
    )
    op.create_index(
        "ix_listing_external_mappings_agent_id",
        "listing_external_mappings",
        ["agent_id"],
    )
    op.create_index(
        "ix_listing_external_mappings_partner_id",
        "listing_external_mappings",
        ["partner_id"],
    )
    op.create_index(
        "ix_listing_external_mappings_tenant_destination",
        "listing_external_mappings",
        ["tenant_id", "destination"],
    )
    op.create_index(
        "ix_listing_external_mappings_dest_external_listing",
        "listing_external_mappings",
        ["destination", "external_listing_id"],
    )


def downgrade():
    op.drop_index("ix_listing_external_mappings_dest_external_listing", table_name="listing_external_mappings")
    op.drop_index("ix_listing_external_mappings_tenant_destination", table_name="listing_external_mappings")
    op.drop_index("ix_listing_external_mappings_partner_id", table_name="listing_external_mappings")
    op.drop_index("ix_listing_external_mappings_agent_id", table_name="listing_external_mappings")
    op.drop_index("ix_listing_external_mappings_listing_id", table_name="listing_external_mappings")
    op.drop_table("listing_external_mappings")

    op.drop_index("ix_agent_external_identities_dest_external_agent", table_name="agent_external_identities")
    op.drop_index("ix_agent_external_identities_partner_id", table_name="agent_external_identities")
    op.drop_index("ix_agent_external_identities_agent_id", table_name="agent_external_identities")
    op.drop_index("ix_agent_external_identities_tenant_destination", table_name="agent_external_identities")
    op.drop_table("agent_external_identities")
