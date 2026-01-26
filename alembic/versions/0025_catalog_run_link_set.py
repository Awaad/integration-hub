from alembic import op
import sqlalchemy as sa

revision = "0025_catalog_run_link_set"
down_revision = "0024_dest_catalog_sets"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "destination_catalog_import_runs",
        sa.Column("catalog_set_id", sa.String(), nullable=True),
    )
    op.create_foreign_key(
        "fk_dest_cat_runs_catalog_set",
        "destination_catalog_import_runs",
        "destination_catalog_sets",
        ["catalog_set_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_catalog_runs_catalog_set",
        "destination_catalog_import_runs",
        ["catalog_set_id"],
        unique=False,
    )

def downgrade():
    op.drop_index("ix_catalog_runs_catalog_set", table_name="destination_catalog_import_runs")
    op.drop_constraint("fk_dest_cat_runs_catalog_set", "destination_catalog_import_runs", type_="foreignkey")
    op.drop_column("destination_catalog_import_runs", "catalog_set_id")
