from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260714_0008"
down_revision = "20260714_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_rules",
        sa.Column("keywords", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("alert_rules", "keywords")
