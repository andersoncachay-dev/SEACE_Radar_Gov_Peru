from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260721_0026"
down_revision = "20260721_0025"
branch_labels = None
depends_on = None

# "Envío de Propuesta" (the last non-outcome stage of Cotización) should show
# the opportunity's real proposal deadline as its due date automatically,
# instead of being left blank for the gestor to type in. This backfills that
# for trackings that were already started before the app started doing this
# automatically at stage-creation time.

BACKFILL_SQL = """
UPDATE opportunity_tracking_stages ots
SET due_date = sub.proposal_deadline
FROM (
    SELECT ots2.id AS stage_id, COALESCE(o.proposal_deadline, o.quote_deadline) AS proposal_deadline
    FROM opportunity_tracking_stages ots2
    JOIN opportunity_trackings ot ON ot.id = ots2.tracking_id
    JOIN opportunities o ON o.id = ot.opportunity_id
    JOIN tracking_phases tp ON tp.id = ots2.phase_id
    WHERE tp.key = 'cotizacion'
      AND ots2.is_outcome_step = false
      AND ots2.due_date IS NULL
      AND ots2.sort_order = (
          SELECT MAX(s3.sort_order)
          FROM opportunity_tracking_stages s3
          WHERE s3.tracking_id = ots2.tracking_id
            AND s3.phase_id = ots2.phase_id
            AND s3.is_outcome_step = false
      )
) sub
WHERE ots.id = sub.stage_id AND sub.proposal_deadline IS NOT NULL
"""


def upgrade() -> None:
    op.execute(sa.text(BACKFILL_SQL))


def downgrade() -> None:
    # One-way data backfill — nothing to revert.
    pass
