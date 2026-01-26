from alembic import op
import sqlalchemy as sa

revision = "0024_dest_catalog_sets"
down_revision = "0023_dest_cat_import_run"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "destination_catalog_sets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("destination", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("country_code", sa.String(length=8), nullable=True),

        sa.Column("status", sa.String(length=16), nullable=False),  # draft|pending|active|rejected|archived
        sa.Column("change_note", sa.Text(), nullable=True),

        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False),
        sa.Column("approved_by", sa.String(length=64), nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_catalog_sets_dest_cc_status_created",
        "destination_catalog_sets",
        ["destination", "country_code", "status", "created_at"],
        unique=False,
    )

    op.create_table(
        "destination_catalog_set_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("catalog_set_id", sa.String(), sa.ForeignKey("destination_catalog_sets.id", ondelete="CASCADE"), nullable=False),

        sa.Column("kind", sa.String(length=16), nullable=False),  # enum|geo
        sa.Column("namespace", sa.String(length=64), nullable=True),  # enum
        sa.Column("source_key", sa.String(length=200), nullable=True),  # enum key
        sa.Column("destination_value", sa.String(length=200), nullable=True),  # enum mapped value

        sa.Column("geo_key", sa.String(length=200), nullable=True),  # "city_slug:area_slug"
        sa.Column("geo_country_code", sa.String(length=8), nullable=True),
        sa.Column("destination_area_id", sa.String(length=200), nullable=True),

        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_catalog_set_items_set", "destination_catalog_set_items", ["catalog_set_id"], unique=False)

    # ensure uniqueness within a set
    op.create_index(
        "uq_catalog_set_item_enum",
        "destination_catalog_set_items",
        ["catalog_set_id", "kind", "namespace", "source_key"],
        unique=True,
        postgresql_where=sa.text("kind = 'enum'"),
    )
    op.create_index(
        "uq_catalog_set_item_geo",
        "destination_catalog_set_items",
        ["catalog_set_id", "kind", "geo_key"],
        unique=True,
        postgresql_where=sa.text("kind = 'geo'"),
    )

    op.create_table(
        "destination_catalog_set_active",
        sa.Column("destination", sa.String(length=64), primary_key=True),
        sa.Column("country_code", sa.String(length=8), primary_key=True, nullable=False, server_default=""),
        sa.Column("active_catalog_set_id", sa.String(), sa.ForeignKey("destination_catalog_sets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

def downgrade():
    op.drop_table("destination_catalog_set_active")
    op.drop_index("uq_catalog_set_item_geo", table_name="destination_catalog_set_items")
    op.drop_index("uq_catalog_set_item_enum", table_name="destination_catalog_set_items")
    op.drop_index("ix_catalog_set_items_set", table_name="destination_catalog_set_items")
    op.drop_table("destination_catalog_set_items")
    op.drop_index("ix_catalog_sets_dest_cc_status_created", table_name="destination_catalog_sets")
    op.drop_table("destination_catalog_sets")
