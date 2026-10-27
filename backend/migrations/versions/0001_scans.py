import sqlalchemy as sa
from alembic import op

revision = "0001_scans"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "monitors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner", sa.String(200), nullable=False),
        sa.Column("domain", sa.String(253), nullable=False),
        sa.Column("interval_hours", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("next_run", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner", "domain", name="uq_monitor_owner_domain"),
    )
    op.create_index("ix_monitors_owner", "monitors", ["owner"])
    op.create_table(
        "scans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner", sa.String(200), nullable=False),
        sa.Column("request_key", sa.String(100), nullable=False),
        sa.Column("domain", sa.String(253), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("result", sa.JSON()),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.UniqueConstraint("owner", "request_key", name="uq_owner_request"),
    )
    op.create_index("ix_scans_owner", "scans", ["owner"])
    op.create_index("ix_scans_domain", "scans", ["domain"])


def downgrade():
    op.drop_index("ix_scans_domain", table_name="scans")
    op.drop_index("ix_scans_owner", table_name="scans")
    op.drop_table("scans")
    op.drop_index("ix_monitors_owner", table_name="monitors")
    op.drop_table("monitors")
