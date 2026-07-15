from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260714_0006"
down_revision = "20260714_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "radar_keywords",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(length=20), nullable=False),
        sa.Column("keyword", sa.String(length=80), nullable=False),
        sa.Column("normalized_keyword", sa.String(length=80), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("country", "normalized_keyword", name="uq_radar_keywords_country_normalized"),
    )
    op.create_index(op.f("ix_radar_keywords_country"), "radar_keywords", ["country"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_radar_keywords_country"), table_name="radar_keywords")
    op.drop_table("radar_keywords")
