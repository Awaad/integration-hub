from alembic import op
import sqlalchemy as sa

revision = "0006_outbox_audit_fields"
down_revision = "0005_add_idempotency_keys"
branch_labels = None
depends_on = None


def upgrade():
    # outbox already has created_at, but it is nullable; make it NOT NULL safely
    op.execute("UPDATE outbox SET created_at = now() WHERE created_at IS NULL;")
    op.alter_column("outbox", "created_at", nullable=False)

    # add missing audit columns
    op.add_column(
        "outbox",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("outbox", sa.Column("created_by", sa.String(), nullable=True))
    op.add_column("outbox", sa.Column("updated_by", sa.String(), nullable=True))


def downgrade():
    op.drop_column("outbox", "updated_by")
    op.drop_column("outbox", "created_by")
    op.drop_column("outbox", "updated_at")
    op.alter_column("outbox", "created_at", nullable=True)
