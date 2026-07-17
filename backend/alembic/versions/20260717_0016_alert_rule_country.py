from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260717_0016"
down_revision = "20260716_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_rules",
        sa.Column("country", sa.String(length=10), nullable=False, server_default="both"),
    )


def downgrade() -> None:
    op.drop_column("alert_rules", "country")
