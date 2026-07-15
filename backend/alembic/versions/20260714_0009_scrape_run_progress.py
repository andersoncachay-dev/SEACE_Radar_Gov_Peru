from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260714_0009"
down_revision = "20260714_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scrape_runs", sa.Column("progress", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("scrape_runs", sa.Column("progress_message", sa.String(length=255), nullable=False, server_default="En cola"))
    op.add_column("scrape_runs", sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("scrape_runs", "cancel_requested")
    op.drop_column("scrape_runs", "progress_message")
    op.drop_column("scrape_runs", "progress")
