from alembic import op
import sqlalchemy as sa

revision = "0007_outbox_processing_fields"
down_revision = "0006_outbox_audit_fields"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("outbox", sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outbox", sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True))

def downgrade():
    op.drop_column("outbox", "processed_at")
    op.drop_column("outbox", "processing_started_at")
