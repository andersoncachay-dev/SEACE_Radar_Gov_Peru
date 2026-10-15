from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261015_0038"
down_revision = "20261014_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hist_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("country", sa.String(length=10), nullable=False, server_default="peru"),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("ref_key", sa.String(length=200), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_hist_comments_country", "hist_comments", ["country"])
    op.create_index("ix_hist_comments_ref", "hist_comments", ["country", "kind", "ref_key"])


def downgrade() -> None:
    op.drop_index("ix_hist_comments_ref", table_name="hist_comments")
    op.drop_index("ix_hist_comments_country", table_name="hist_comments")
    op.drop_table("hist_comments")
