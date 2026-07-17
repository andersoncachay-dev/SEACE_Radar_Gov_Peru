from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260715_0014"
down_revision = "20260715_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunity_view_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=80), nullable=False),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_id", "scope", name="uq_opportunity_view_states_owner_scope"),
    )
    op.create_index(op.f("ix_opportunity_view_states_owner_id"), "opportunity_view_states", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_opportunity_view_states_owner_id"), table_name="opportunity_view_states")
    op.drop_table("opportunity_view_states")
