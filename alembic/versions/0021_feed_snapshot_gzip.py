from alembic import op
import sqlalchemy as sa

revision = "0021_feed_snapshot_gzip"
down_revision = "0020_destination_enum_map"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("feed_snapshots", sa.Column("gzip_storage_uri", sa.Text(), nullable=True))
    op.add_column("feed_snapshots", sa.Column("gzip_size_bytes", sa.Integer(), nullable=True))

def downgrade():
    op.drop_column("feed_snapshots", "gzip_size_bytes")
    op.drop_column("feed_snapshots", "gzip_storage_uri")
