from alembic import op
import sqlalchemy as sa

revision = "0030_listing_media_normalized_hash"
down_revision = "0029_list_med_norm_retry_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "listings",
        sa.Column("media_normalized_hash", sa.String(length=80), nullable=True),
    )
    op.create_index(
        "ix_listings_media_normalized_hash",
        "listings",
        ["media_normalized_hash"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_listings_media_normalized_hash", table_name="listings")
    op.drop_column("listings", "media_normalized_hash")