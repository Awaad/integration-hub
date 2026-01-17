from alembic import op
import sqlalchemy as sa

revision = "0019_destination_geo_mappings"
down_revision = "0018_geo_catalogs"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "destination_geo_mappings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("destination", sa.String(length=120), nullable=False),
        sa.Column("geo_country_id", sa.String(), sa.ForeignKey("geo_countries.id"), nullable=True),
        sa.Column("geo_city_id", sa.String(), sa.ForeignKey("geo_cities.id"), nullable=True),
        sa.Column("geo_area_id", sa.String(), sa.ForeignKey("geo_areas.id"), nullable=True),
        sa.Column("destination_city_id", sa.String(length=64), nullable=True),
        sa.Column("destination_area_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.UniqueConstraint("destination", "geo_area_id", name="uq_dest_geo_area"),
    )
    op.create_index("ix_dest_geo_dest", "destination_geo_mappings", ["destination"])
    op.create_index("ix_dest_geo_area", "destination_geo_mappings", ["geo_area_id"])

def downgrade():
    op.drop_index("ix_dest_geo_area", table_name="destination_geo_mappings")
    op.drop_index("ix_dest_geo_dest", table_name="destination_geo_mappings")
    op.drop_table("destination_geo_mappings")
