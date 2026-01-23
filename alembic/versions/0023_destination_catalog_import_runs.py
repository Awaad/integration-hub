from alembic import op
import sqlalchemy as sa

revision = "0023_dest_cat_import_run"
down_revision = "0022_audit_logs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "destination_catalog_import_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("destination", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),  # enum|geo
        sa.Column("namespace", sa.String(length=64), nullable=True),  # enum only
        sa.Column("country_code", sa.String(length=8), nullable=True),  # geo only
        sa.Column("source", sa.String(length=200), nullable=True),  # e.g. "101evler_pdf_v2026_01"
        sa.Column("status", sa.String(length=16), nullable=False),  # previewed|applied|failed
        sa.Column("summary", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "ix_catalog_runs_dest_kind_ns_cc_created",
        "destination_catalog_import_runs",
        ["destination", "kind", "namespace", "country_code", "created_at"],
        unique=False,
    )

    op.create_table(
        "destination_catalog_import_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("run_id", sa.String(), sa.ForeignKey("destination_catalog_import_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),    # enum source_key OR "city:area"
        sa.Column("value", sa.String(length=200), nullable=True),   # destination_value / destination_area_id
        sa.Column("existing_value", sa.String(length=200), nullable=True),
        sa.Column("action", sa.String(length=16), nullable=False),  # insert|update|noop|invalid
        sa.Column("detail", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_catalog_items_run", "destination_catalog_import_items", ["run_id"], unique=False)
    op.create_index("ix_catalog_items_action", "destination_catalog_import_items", ["action"], unique=False)


def downgrade():
    op.drop_index("ix_catalog_items_action", table_name="destination_catalog_import_items")
    op.drop_index("ix_catalog_items_run", table_name="destination_catalog_import_items")
    op.drop_table("destination_catalog_import_items")

    op.drop_index("ix_catalog_runs_dest_kind_ns_cc_created", table_name="destination_catalog_import_runs")
    op.drop_table("destination_catalog_import_runs")
