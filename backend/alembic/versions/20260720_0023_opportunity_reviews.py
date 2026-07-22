from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260720_0023"
down_revision = "20260720_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunity_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="standby"),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["resolved_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("opportunity_id"),
    )
    op.create_index(op.f("ix_opportunity_reviews_opportunity_id"), "opportunity_reviews", ["opportunity_id"], unique=True)

    op.create_table(
        "opportunity_review_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_opportunity_review_comments_opportunity_id"), "opportunity_review_comments", ["opportunity_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_opportunity_review_comments_opportunity_id"), table_name="opportunity_review_comments")
    op.drop_table("opportunity_review_comments")
    op.drop_index(op.f("ix_opportunity_reviews_opportunity_id"), table_name="opportunity_reviews")
    op.drop_table("opportunity_reviews")
