from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260717_0018"
down_revision = "20260717_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("source_status", sa.String(length=60), nullable=False, server_default=""))
    op.add_column("opportunities", sa.Column("contract_duration", sa.String(length=60), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("opportunities", "contract_duration")
    op.drop_column("opportunities", "source_status")
