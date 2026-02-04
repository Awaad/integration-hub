from alembic import op
import sqlalchemy as sa

revision = "0027_partner_public_tokens"
down_revision = "0026_media_objects"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "partner_public_tokens",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("partner_id", sa.String(), nullable=False),

        sa.Column("scope", sa.String(length=32), nullable=False),  # "media"
        sa.Column("token_prefix", sa.String(length=12), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_ciphertext", sa.Text(), nullable=False),

        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),

        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_index("ix_partner_public_tokens_partner_scope", "partner_public_tokens", ["tenant_id", "partner_id", "scope"], unique=False)
    op.create_index(
        "uq_partner_public_tokens_active_scope",
        "partner_public_tokens",
        ["tenant_id", "partner_id", "scope"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade():
    op.drop_index("uq_partner_public_tokens_active_scope", table_name="partner_public_tokens")
    op.drop_index("ix_partner_public_tokens_partner_scope", table_name="partner_public_tokens")
    op.drop_table("partner_public_tokens")
