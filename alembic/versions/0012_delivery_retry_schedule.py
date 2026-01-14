from alembic import op
import sqlalchemy as sa

revision = "0012_delivery_retry_schedule"
down_revision = "0011_external_identities"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("deliveries", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "deliveries",
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index(
        "ix_deliveries_status_next_retry_at",
        "deliveries",
        ["status", "next_retry_at"],
    )


def downgrade():
    op.drop_index("ix_deliveries_status_next_retry_at", table_name="deliveries")
    op.drop_column("deliveries", "retryable")
    op.drop_column("deliveries", "next_retry_at")
