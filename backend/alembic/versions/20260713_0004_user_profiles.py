from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260713_0004"
down_revision = "20260713_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("first_name", sa.String(length=120), nullable=False, server_default=""))
    op.add_column("users", sa.Column("last_name", sa.String(length=160), nullable=False, server_default=""))
    op.add_column("users", sa.Column("position", sa.String(length=160), nullable=False, server_default=""))
    op.add_column("users", sa.Column("address", sa.String(length=255), nullable=False, server_default=""))
    op.add_column("users", sa.Column("phone_peru", sa.String(length=32), nullable=False, server_default=""))
    op.add_column("users", sa.Column("phone_chile", sa.String(length=32), nullable=False, server_default=""))
    op.add_column("users", sa.Column("access_profile", sa.String(length=20), nullable=False, server_default="peru"))
    op.execute("UPDATE users SET first_name = full_name WHERE first_name = ''")
    op.execute("UPDATE users SET access_profile = 'both' WHERE role = 'admin'")


def downgrade() -> None:
    op.drop_column("users", "access_profile")
    op.drop_column("users", "phone_chile")
    op.drop_column("users", "phone_peru")
    op.drop_column("users", "address")
    op.drop_column("users", "position")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
