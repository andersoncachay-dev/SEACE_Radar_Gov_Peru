from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260716_0015"
down_revision = "20260715_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "opportunities",
        sa.Column("schedule_source", sa.String(length=40), nullable=False, server_default=""),
    )
    op.add_column(
        "opportunities",
        sa.Column("schedule_validated_at", sa.DateTime(), nullable=True),
    )

    # Legacy Peru deadlines have no trustworthy provenance: some came from
    # OCDS and some were corrupted by the former ISO/day-first conversion.
    # Hide them until SEACE/SV3 supplies the authoritative schedule again.
    op.execute(
        sa.text(
            """
            UPDATE opportunities
               SET consultation_deadline = NULL,
                   quote_deadline = NULL,
                   proposal_deadline = NULL,
                   status = 'Revisar cronograma SEACE',
                   schedule_source = '',
                   schedule_validated_at = NULL
             WHERE source = 'oece_ocds_api'
               AND is_archived = false
            """
        )
    )


def downgrade() -> None:
    op.drop_column("opportunities", "schedule_validated_at")
    op.drop_column("opportunities", "schedule_source")
