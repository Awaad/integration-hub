from alembic import op
import sqlalchemy as sa

revision = "0015_ingest_runs_adapter_version"
down_revision = "0014_ingest_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ingest_runs", sa.Column("adapter_version", sa.String(length=40), nullable=False, server_default=""))
   

def downgrade():
    op.drop_column("ingest_runs", "adapter_version")
