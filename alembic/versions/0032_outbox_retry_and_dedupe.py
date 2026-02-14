from alembic import op
import sqlalchemy as sa

revision = "0032_outbox_retry_and_dedupe"
down_revision = "0031_partner_settings"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("outbox", sa.Column("dedupe_key", sa.String(length=512), nullable=True))
    op.add_column("outbox", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outbox", sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True))

    # Dedupe only for "active" in-flight rows (allows manual re-enqueue after done/dead)
    op.create_index(
        "uq_outbox_dedupe_key_active",
        "outbox",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text(
            "dedupe_key IS NOT NULL "
            "AND dead_lettered_at IS NULL "
            "AND status IN ('pending','processing')"
        ),
    )

    # Claim path: pending + due ordering
    op.create_index(
        "ix_outbox_pending_due",
        "outbox",
        ["status", "next_retry_at", "created_at"],
        unique=False,
    )

    # Reclaim stale processing leases efficiently
    op.create_index(
        "ix_outbox_processing_lease_expires",
        "outbox",
        ["status", "lease_expires_at"],
        unique=False,
    )

    # Often useful
    op.create_index(
        "ix_outbox_aggregate",
        "outbox",
        ["aggregate_type", "aggregate_id", "created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_outbox_aggregate", table_name="outbox")
    op.drop_index("ix_outbox_processing_lease_expires", table_name="outbox")
    op.drop_index("ix_outbox_pending_due", table_name="outbox")
    op.drop_index("uq_outbox_dedupe_key_active", table_name="outbox")

    op.drop_column("outbox", "dead_lettered_at")
    op.drop_column("outbox", "next_retry_at")
    op.drop_column("outbox", "dedupe_key")