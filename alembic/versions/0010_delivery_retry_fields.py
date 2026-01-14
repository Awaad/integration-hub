from alembic import op
import sqlalchemy as sa

revision = "0010_delivery_retry_fields"
down_revision = "0009_outbox_leases"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("deliveries", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("deliveries", sa.Column("status_detail", sa.Text(), nullable=True))
    op.add_column("deliveries", sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_deliveries_status_attempts", "deliveries", ["status", "attempts"])

def downgrade():
    op.drop_index("ix_deliveries_status_attempts", table_name="deliveries")
    op.drop_column("deliveries", "dead_lettered_at")
    op.drop_column("deliveries", "status_detail")
    op.drop_column("deliveries", "attempts")
