from alembic import op
import sqlalchemy as sa

revision = "0029_list_med_norm_retry_fields"
down_revision = "0028_media_variants"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("listings", sa.Column("media_normalized_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("listings", sa.Column("media_normalization_error", sa.Text(), nullable=True))
    op.add_column(
        "listings",
        sa.Column("media_normalization_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("listings", sa.Column("media_normalization_next_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("listings", sa.Column("media_normalization_started_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_listings_media_normalized_at", "listings", ["media_normalized_at"], unique=False)
    op.create_index(
        "ix_listings_media_norm_due",
        "listings",
        ["media_normalization_next_at", "media_normalized_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_listings_media_norm_due", table_name="listings")
    op.drop_index("ix_listings_media_normalized_at", table_name="listings")

    op.drop_column("listings", "media_normalization_started_at")
    op.drop_column("listings", "media_normalization_next_at")
    op.drop_column("listings", "media_normalization_attempts")
    op.drop_column("listings", "media_normalization_error")
    op.drop_column("listings", "media_normalized_at")
