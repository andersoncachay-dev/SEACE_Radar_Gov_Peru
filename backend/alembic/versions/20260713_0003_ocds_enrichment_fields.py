from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260713_0003"
down_revision = "20260711_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("buyer_ruc", sa.String(length=30), nullable=False, server_default=""))
    op.add_column("opportunities", sa.Column("ocid", sa.String(length=220), nullable=False, server_default=""))
    op.add_column("opportunities", sa.Column("tender_id", sa.String(length=180), nullable=False, server_default=""))
    op.add_column("opportunities", sa.Column("ocds_source_id", sa.String(length=80), nullable=False, server_default=""))
    op.add_column("opportunities", sa.Column("release_id", sa.String(length=220), nullable=False, server_default=""))
    op.add_column("opportunities", sa.Column("documents_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("opportunities", "documents_count")
    op.drop_column("opportunities", "release_id")
    op.drop_column("opportunities", "ocds_source_id")
    op.drop_column("opportunities", "tender_id")
    op.drop_column("opportunities", "ocid")
    op.drop_column("opportunities", "buyer_ruc")
