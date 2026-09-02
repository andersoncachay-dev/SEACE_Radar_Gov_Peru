from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260902_0034"
down_revision = "20260805_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "access_profile", type_=sa.String(length=40), existing_type=sa.String(length=20))
    op.execute("UPDATE users SET access_profile = 'peru,chile,argentina' WHERE access_profile = 'both'")


def downgrade() -> None:
    op.execute("UPDATE users SET access_profile = 'both' WHERE access_profile = 'peru,chile,argentina'")
    op.alter_column("users", "access_profile", type_=sa.String(length=20), existing_type=sa.String(length=40))
