from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261014_0036"
down_revision = "20261012_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_favorites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("ref_key", sa.String(length=200), nullable=False),
        sa.Column("label", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "kind", "ref_key", name="uq_user_favorites_user_kind_ref"),
    )
    op.create_index("ix_user_favorites_user_id", "user_favorites", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_favorites_user_id", table_name="user_favorites")
    op.drop_table("user_favorites")
