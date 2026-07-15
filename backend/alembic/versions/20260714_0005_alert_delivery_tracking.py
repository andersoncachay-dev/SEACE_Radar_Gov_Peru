from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260714_0005"
down_revision = "20260713_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("alerts", sa.Column("next_attempt_at", sa.DateTime(), nullable=True))
    op.add_column("alerts", sa.Column("last_attempt_at", sa.DateTime(), nullable=True))
    op.add_column("alerts", sa.Column("last_error", sa.Text(), nullable=False, server_default=""))
    op.add_column("alerts", sa.Column("provider_message_id", sa.String(length=255), nullable=False, server_default=""))
    op.execute("UPDATE alerts SET message = split_part(message, E'\\n\\nDelivery error:', 1) WHERE message LIKE '%Delivery error:%'")
    op.execute("UPDATE alerts SET status = 'retrying' WHERE status = 'error'")


def downgrade() -> None:
    op.drop_column("alerts", "provider_message_id")
    op.drop_column("alerts", "last_error")
    op.drop_column("alerts", "last_attempt_at")
    op.drop_column("alerts", "next_attempt_at")
    op.drop_column("alerts", "attempt_count")
