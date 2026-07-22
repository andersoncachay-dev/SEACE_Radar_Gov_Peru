from __future__ import annotations

from datetime import timedelta

from alembic import op
import sqlalchemy as sa

revision = "20260721_0027"
down_revision = "20260721_0026"
branch_labels = None
depends_on = None

# Recompute due dates for Cotización's stages using a weighted split of the
# real publication_date -> proposal_deadline window: "Cotización" itself gets
# 40% of the time, the remaining 60% is split equally among the other
# stages, in order. This mirrors tracking_service.compute_cotizacion_due_dates
# (kept in sync manually — migrations must stay self-contained and not import
# app code, since app code can change after this migration ships).
#
# Only touches stages that are NOT completed yet, so finished work keeps its
# historical dates.


def upgrade() -> None:
    connection = op.get_bind()

    phase_ids = [row.id for row in connection.execute(sa.text("SELECT id FROM tracking_phases WHERE key = 'cotizacion'"))]
    if not phase_ids:
        return

    for phase_id in phase_ids:
        templates = list(
            connection.execute(
                sa.text(
                    "SELECT id, name, sort_order FROM tracking_stage_templates "
                    "WHERE phase_id = :phase_id AND is_active = true AND is_outcome_step = false "
                    "ORDER BY sort_order"
                ),
                {"phase_id": phase_id},
            )
        )
        if not templates:
            continue

        cotizacion_template = next((t for t in templates if t.name.strip().lower() == "cotización"), None)
        weights: dict[int, float] = {}
        if cotizacion_template:
            weights[cotizacion_template.id] = 0.40
            others = [t for t in templates if t.id != cotizacion_template.id]
            remaining = 0.60
        else:
            others = templates
            remaining = 1.0
        if others:
            share = remaining / len(others)
            for template in others:
                weights[template.id] = share

        trackings = list(
            connection.execute(
                sa.text(
                    "SELECT ot.id AS tracking_id, o.publication_date, o.proposal_deadline, o.quote_deadline "
                    "FROM opportunity_trackings ot "
                    "JOIN opportunities o ON o.id = ot.opportunity_id "
                    "WHERE ot.current_phase_id = :phase_id "
                    "   OR EXISTS (SELECT 1 FROM opportunity_tracking_stages s WHERE s.tracking_id = ot.id AND s.phase_id = :phase_id)"
                ),
                {"phase_id": phase_id},
            )
        )

        for tracking in trackings:
            range_start = tracking.publication_date
            range_end = tracking.proposal_deadline or tracking.quote_deadline
            if not range_start or not range_end:
                continue
            total_seconds = (range_end - range_start).total_seconds()
            if total_seconds <= 0:
                continue

            cumulative = 0.0
            for template in templates:
                cumulative += weights.get(template.id, 0.0)
                due_date = range_start + timedelta(seconds=total_seconds * cumulative)
                connection.execute(
                    sa.text(
                        "UPDATE opportunity_tracking_stages SET due_date = :due_date "
                        "WHERE tracking_id = :tracking_id AND stage_template_id = :template_id AND completed = false"
                    ),
                    {"due_date": due_date, "tracking_id": tracking.tracking_id, "template_id": template.id},
                )


def downgrade() -> None:
    # One-way data backfill — nothing to revert.
    pass
