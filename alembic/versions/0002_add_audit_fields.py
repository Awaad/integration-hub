from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0002_add_audit_fields"
down_revision = "0001_phase0_foundations"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def _add_if_missing(table: str, column: sa.Column) -> None:
    if not _has_column(table, column.name):
        op.add_column(table, column)


def upgrade():
    for table in ["tenants", "partners", "agents", "api_keys"]:
        _add_if_missing(
            table,
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        _add_if_missing(
            table,
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        _add_if_missing(table, sa.Column("created_by", sa.String(), nullable=True))
        _add_if_missing(table, sa.Column("updated_by", sa.String(), nullable=True))

    # create indexes only if they don't already exist
    bind = op.get_bind()
    insp = inspect(bind)

    agents_ix = {ix["name"] for ix in insp.get_indexes("agents")}
    if "ix_agents_updated_at" not in agents_ix:
        op.create_index("ix_agents_updated_at", "agents", ["updated_at"])

    api_keys_ix = {ix["name"] for ix in insp.get_indexes("api_keys")}
    if "ix_api_keys_updated_at" not in api_keys_ix:
        op.create_index("ix_api_keys_updated_at", "api_keys", ["updated_at"])


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    api_keys_ix = {ix["name"] for ix in insp.get_indexes("api_keys")}
    if "ix_api_keys_updated_at" in api_keys_ix:
        op.drop_index("ix_api_keys_updated_at", table_name="api_keys")

    agents_ix = {ix["name"] for ix in insp.get_indexes("agents")}
    if "ix_agents_updated_at" in agents_ix:
        op.drop_index("ix_agents_updated_at", table_name="agents")

    for table in ["api_keys", "agents", "partners", "tenants"]:
        for col in ["updated_by", "created_by", "updated_at", "created_at"]:
            if _has_column(table, col):
                op.drop_column(table, col)