from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260715_0013"
down_revision = "20260714_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("app_settings", "value", existing_type=sa.String(length=255), type_=sa.Text(), nullable=False)


def downgrade() -> None:
    op.alter_column("app_settings", "value", existing_type=sa.Text(), type_=sa.String(length=255), nullable=False)
