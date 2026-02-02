from alembic import op
import sqlalchemy as sa

revision = "0026_media_objects"
down_revision = "0025_catalog_run_link_set"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "media_objects",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("partner_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False),

        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),

        sa.Column("storage_backend", sa.String(length=32), nullable=False),
        sa.Column("storage_key", sa.String(length=400), nullable=False),

        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),

        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_check_constraint("ck_media_objects_byte_size_positive", "media_objects", "byte_size > 0",)

    op.create_index("ix_media_objects_tenant_created", "media_objects", ["tenant_id", "created_at"])
    op.create_index("ix_media_objects_owner_created", "media_objects", ["tenant_id", "partner_id", "agent_id","created_at"],)
    op.create_index("uq_media_objects_owner_hash", "media_objects", ["tenant_id", "partner_id", "agent_id", "content_hash"], unique=True,)

    op.create_table(
        "listing_media",
        sa.Column("id", sa.String(), primary_key=True),

        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("partner_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False),

        sa.Column("listing_id", sa.String(), sa.ForeignKey("listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_id", sa.String(), sa.ForeignKey("media_objects.id", ondelete="CASCADE"), nullable=False),

        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),

        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_index("ix_listing_media_listing", "listing_media", ["listing_id"])
    op.create_index("ix_listing_media_owner", "listing_media", ["tenant_id", "partner_id", "agent_id", "listing_id"])
    op.create_index("ix_listing_media_listing_order", "listing_media", ["listing_id", "order_index", "created_at"],)
    op.create_index("uq_listing_media_primary_per_listing", "listing_media", ["listing_id"], unique=True, postgresql_where=sa.text("is_primary = true"),)
    op.create_index("uq_listing_media_listing_media", "listing_media", ["tenant_id", "partner_id", "agent_id", "listing_id", "media_id"], unique=True)


def downgrade():
    op.drop_index("ix_listing_media_owner", table_name="listing_media")
    op.drop_index("uq_listing_media_listing_media", table_name="listing_media")
    op.drop_index("uq_listing_media_primary_per_listing", table_name="listing_media")
    op.drop_index("ix_listing_media_listing_order", table_name="listing_media")
    op.drop_index("ix_listing_media_listing", table_name="listing_media")
    op.drop_table("listing_media")

    op.drop_index("uq_media_objects_owner_hash", table_name="media_objects")
    op.drop_index("ix_media_objects_owner_created", table_name="media_objects")
    op.drop_index("ix_media_objects_tenant_created", table_name="media_objects")
    op.drop_constraint("ck_media_objects_byte_size_positive", "media_objects", type_="check")
    op.drop_table("media_objects")
