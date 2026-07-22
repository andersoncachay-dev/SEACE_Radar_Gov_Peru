from __future__ import annotations

from datetime import timedelta

from alembic import op
import sqlalchemy as sa

revision = "20260721_0028"
down_revision = "20260721_0027"
branch_labels = None
depends_on = None

# 1) Renombra la etapa "Levantamiento de necesidades" a "Registro de participación":
#    el levantamiento de necesidades real ya ocurre antes, en el módulo Oportunidades.
# 2) Recalcula las fechas de Cotización anclándolas a fechas OFICIALES reales del
#    portal en vez de repartirlas por porcentaje: Consultas -> consultation_deadline
#    real (SEACE/Mercado Público), Envío de Propuesta -> proposal_deadline/
#    quote_deadline real, Registro de participación -> fecha de inicio del
#    seguimiento. Cualquier etapa intermedia sin fecha oficial propia (ej.
#    "Cotización") se reparte dentro de la ventana entre la última ancla conocida y
#    el cierre de propuesta, terminando siempre 1 día antes de ese cierre. Mirrors
#    tracking_service.compute_cotizacion_due_dates (kept in sync manually — migrations
#    must stay self-contained and not import app code).
#
# Solo toca etapas NO completadas de trackings activos, para no reescribir historial.

OLD_NAME = "Levantamiento de necesidades"
NEW_NAME = "Registro de participación"


def upgrade() -> None:
    connection = op.get_bind()

    connection.execute(
        sa.text("UPDATE tracking_stage_templates SET name = :new WHERE name = :old"),
        {"new": NEW_NAME, "old": OLD_NAME},
    )
    connection.execute(
        sa.text("UPDATE opportunity_tracking_stages SET name = :new WHERE name = :old"),
        {"new": NEW_NAME, "old": OLD_NAME},
    )

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

        consultas_template = next((t for t in templates if "consulta" in t.name.strip().lower()), None)
        last_template = templates[-1]

        trackings = list(
            connection.execute(
                sa.text(
                    "SELECT ot.id AS tracking_id, ot.started_at, o.consultation_deadline, "
                    "o.proposal_deadline, o.quote_deadline "
                    "FROM opportunity_trackings ot "
                    "JOIN opportunities o ON o.id = ot.opportunity_id "
                    "WHERE ot.status = 'active' "
                    "  AND EXISTS (SELECT 1 FROM opportunity_tracking_stages s WHERE s.tracking_id = ot.id AND s.phase_id = :phase_id)"
                ),
                {"phase_id": phase_id},
            )
        )

        for tracking in trackings:
            proposal_deadline = tracking.proposal_deadline or tracking.quote_deadline
            due_dates: dict[int, object] = {}

            if tracking.started_at is not None:
                due_dates[templates[0].id] = tracking.started_at
            if consultas_template and tracking.consultation_deadline is not None:
                due_dates[consultas_template.id] = tracking.consultation_deadline

            if proposal_deadline is not None:
                due_dates[last_template.id] = proposal_deadline

                window_end = proposal_deadline - timedelta(days=1)
                window_start = due_dates.get(consultas_template.id) if consultas_template else None
                if window_start is None:
                    window_start = tracking.started_at
                pending = [t for t in templates if t.id not in due_dates]
                if pending:
                    if window_start is not None and window_end > window_start:
                        total_seconds = (window_end - window_start).total_seconds()
                        share = total_seconds / len(pending)
                        for index, template in enumerate(pending, start=1):
                            due_dates[template.id] = window_start + timedelta(seconds=share * index)
                    else:
                        for template in pending:
                            due_dates[template.id] = window_end

            for template_id, due_date in due_dates.items():
                connection.execute(
                    sa.text(
                        "UPDATE opportunity_tracking_stages SET due_date = :due_date "
                        "WHERE tracking_id = :tracking_id AND stage_template_id = :template_id AND completed = false"
                    ),
                    {"due_date": due_date, "tracking_id": tracking.tracking_id, "template_id": template_id},
                )


def downgrade() -> None:
    # One-way data backfill / rename — nothing to revert.
    pass
