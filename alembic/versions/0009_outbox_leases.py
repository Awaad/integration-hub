from alembic import op
import sqlalchemy as sa

revision = "0009_outbox_leases"
down_revision = "0008_deliveries"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("outbox", sa.Column("lease_id", sa.String(length=64), nullable=True))
    op.add_column("outbox", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_outbox_lease_expires", "outbox", ["status", "lease_expires_at"])


def downgrade():
    op.drop_index("ix_outbox_lease_expires", table_name="outbox")
    op.drop_column("outbox", "lease_expires_at")
    op.drop_column("outbox", "lease_id")
