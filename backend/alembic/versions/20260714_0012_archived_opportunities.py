from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260714_0012"
down_revision = "20260714_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("is_archived", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("opportunities", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.add_column("opportunities", sa.Column("archived_by_id", sa.Integer(), nullable=True))
    op.add_column("opportunities", sa.Column("archive_country", sa.String(length=10), server_default="", nullable=False))
    op.add_column("opportunities", sa.Column("archive_key", sa.String(length=180), server_default="", nullable=False))
    op.create_foreign_key(
        "fk_opportunities_archived_by_id_users",
        "opportunities",
        "users",
        ["archived_by_id"],
        ["id"],
    )
    op.create_index(op.f("ix_opportunities_is_archived"), "opportunities", ["is_archived"], unique=False)
    op.create_index(
        "ix_opportunities_archive_lookup",
        "opportunities",
        ["is_archived", "archive_country", "archive_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_opportunities_archive_lookup", table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_is_archived"), table_name="opportunities")
    op.drop_constraint("fk_opportunities_archived_by_id_users", "opportunities", type_="foreignkey")
    op.drop_column("opportunities", "archive_key")
    op.drop_column("opportunities", "archive_country")
    op.drop_column("opportunities", "archived_by_id")
    op.drop_column("opportunities", "archived_at")
    op.drop_column("opportunities", "is_archived")
