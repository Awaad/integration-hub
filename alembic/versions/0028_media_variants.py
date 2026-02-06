from alembic import op
import sqlalchemy as sa

revision = "0028_media_variants"
down_revision = "0027_partner_public_tokens"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "media_variants",
        sa.Column("id", sa.String(), primary_key=True),

        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("partner_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False),

        sa.Column("media_id", sa.String(), sa.ForeignKey("media_objects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant", sa.String(length=32), nullable=False),  # thumb|medium|large

        sa.Column("variant_hash", sa.String(length=64), nullable=False),  # sha256 hex

        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),

        sa.Column("storage_backend", sa.String(length=32), nullable=False),
        sa.Column("storage_key", sa.String(length=400), nullable=False),

        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_check_constraint(
        "ck_media_variants_byte_size_positive",
        "media_variants",
        "byte_size > 0",
    )

    op.create_index("uq_media_variants_media_variant", "media_variants", ["media_id", "variant"], unique=True)
    op.create_index("ix_media_variants_media", "media_variants", ["media_id"], unique=False)
    op.create_index("ix_media_variants_owner_created", "media_variants", ["tenant_id", "partner_id", "agent_id", "created_at"], unique=False)

def downgrade():
    op.drop_index("ix_media_variants_owner_created", table_name="media_variants")
    op.drop_index("ix_media_variants_media", table_name="media_variants")
    op.drop_index("uq_media_variants_media_variant", table_name="media_variants")
    op.drop_constraint("ck_media_variants_byte_size_positive", "media_variants", type_="check")
    op.drop_table("media_variants")
