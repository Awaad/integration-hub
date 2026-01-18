from alembic import op
import sqlalchemy as sa

revision = "0020_destination_enum_map"
down_revision = "0019_destination_geo_mappings"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "destination_enum_mappings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("destination", sa.String(length=120), nullable=False),
        sa.Column("namespace", sa.String(length=80), nullable=False),
        sa.Column("source_key", sa.String(length=180), nullable=False),
        sa.Column("destination_value", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.UniqueConstraint("destination", "namespace", "source_key", name="uq_dest_enum_map"),
    )
    op.create_index("ix_dest_enum_dest_ns", "destination_enum_mappings", ["destination", "namespace"])

def downgrade():
    op.drop_index("ix_dest_enum_dest_ns", table_name="destination_enum_mappings")
    op.drop_table("destination_enum_mappings")
