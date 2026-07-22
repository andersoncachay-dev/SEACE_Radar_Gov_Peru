from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260721_0025"
down_revision = "20260721_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("opportunity_trackings", sa.Column("co_responsible_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_opportunity_trackings_co_responsible_id_users",
        "opportunity_trackings",
        "users",
        ["co_responsible_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_opportunity_trackings_co_responsible_id_users", "opportunity_trackings", type_="foreignkey")
    op.drop_column("opportunity_trackings", "co_responsible_id")
