from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014_ingest_runs"
down_revision = "0013_source_listing_mappings"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("partner_id", sa.String(), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("partner_key", sa.String(length=80), nullable=False),
        sa.Column("source_listing_id", sa.String(length=200), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),

        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("canonical_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),

        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("listing_id", sa.String(), sa.ForeignKey("listings.id"), nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),

        sa.UniqueConstraint(
            "tenant_id", "partner_id", "partner_key", "source_listing_id", "idempotency_key",
            name="uq_ingest_run_idempotency"
        ),
    )

    op.create_index("ix_ingest_runs_partner_source", "ingest_runs", ["partner_key", "source_listing_id"])
    op.create_index("ix_ingest_runs_listing_id", "ingest_runs", ["listing_id"])
    op.create_index("ix_ingest_runs_created_at", "ingest_runs", ["created_at"])


def downgrade():
    op.drop_index("ix_ingest_runs_created_at", table_name="ingest_runs")
    op.drop_index("ix_ingest_runs_listing_id", table_name="ingest_runs")
    op.drop_index("ix_ingest_runs_partner_source", table_name="ingest_runs")
    op.drop_table("ingest_runs")
