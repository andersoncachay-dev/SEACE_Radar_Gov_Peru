from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260721_0029"
down_revision = "20260721_0028"
branch_labels = None
depends_on = None

# Per-stage switches to enable/disable automatic "Atender"/"Urgente" time-status
# email reminders (sent to the owner + co-responsible), plus a ratchet field to
# avoid re-sending the same tier's alert on every scheduler tick.


def upgrade() -> None:
    op.add_column(
        "opportunity_tracking_stages",
        sa.Column("alert_atender_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "opportunity_tracking_stages",
        sa.Column("alert_urgente_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "opportunity_tracking_stages",
        sa.Column("last_time_alert_status", sa.String(length=20), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("opportunity_tracking_stages", "last_time_alert_status")
    op.drop_column("opportunity_tracking_stages", "alert_urgente_enabled")
    op.drop_column("opportunity_tracking_stages", "alert_atender_enabled")
