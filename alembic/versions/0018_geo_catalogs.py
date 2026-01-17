from alembic import op
import sqlalchemy as sa

revision = "0018_geo_catalogs"
down_revision = "0017_feed_snapshots"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "geo_countries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_geo_country_code"),
    )

    op.create_table(
        "geo_cities",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("country_id", sa.String(), sa.ForeignKey("geo_countries.id"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("country_id", "slug", name="uq_geo_city_slug"),
    )

    op.create_table(
        "geo_areas",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("city_id", sa.String(), sa.ForeignKey("geo_cities.id"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("city_id", "slug", name="uq_geo_area_slug"),
    )

    op.create_index("ix_geo_city_country", "geo_cities", ["country_id"])
    op.create_index("ix_geo_area_city", "geo_areas", ["city_id"])

def downgrade():
    op.drop_index("ix_geo_area_city", table_name="geo_areas")
    op.drop_index("ix_geo_city_country", table_name="geo_cities")
    op.drop_table("geo_areas")
    op.drop_table("geo_cities")
    op.drop_table("geo_countries")
