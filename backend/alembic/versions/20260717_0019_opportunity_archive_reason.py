from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260717_0019"
down_revision = "20260717_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("archive_reason", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("opportunities", "archive_reason")
