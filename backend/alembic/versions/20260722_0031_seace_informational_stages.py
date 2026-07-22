from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "20260722_0031"
down_revision = "20260721_0030"
branch_labels = None
depends_on = None

# Perú (solo Perú -Chile no tiene estas etapas en su cronograma de Mercado Público)
# tiene tramos del cronograma SEACE que no requieren gestión comercial propia -son
# puramente informativos, hay que esperar a que la entidad los publique-, pero sí
# aportan trazabilidad completa del proceso si se muestran y se revalidan junto con
# el resto de fechas. El scraper (src/seace_browser_scraper.py) ya trae estos campos
# del cronograma completo (absolucion_fin, integracion_fin, evaluacion_fin,
# buena_pro_fin); tracking_date_refresh_service._refresh_peru pasa a usarlos.
#
# Las 4 etapas existentes de Cotización mantienen su sort_order (multiplicado x10
# para dejar hueco) y sus datos intactos -esto NO reescribe due_date/status/completed/
# áreas/responsables de ningún tracking activo, solo reordena y agrega filas nuevas-.
# Los trackings ya iniciados para Perú reciben las 4 etapas informativas nuevas sin
# necesidad de reiniciarlos.

INFORMATIONAL_STAGES = [
    {"name": "Absolución de Consultas y Observaciones", "sort_order": 25},
    {"name": "Integración de las Bases", "sort_order": 28},
    {"name": "Calificación y Evaluación de Propuestas", "sort_order": 45},
    {"name": "Otorgamiento de la Buena Pro", "sort_order": 48},
]


def upgrade() -> None:
    op.add_column(
        "tracking_stage_templates",
        sa.Column("is_informational", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "opportunity_tracking_stages",
        sa.Column("is_informational", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    connection = op.get_bind()
    now = datetime.utcnow()

    phase_id = connection.execute(
        sa.text("SELECT id FROM tracking_phases WHERE country = 'peru' AND key = 'cotizacion'")
    ).scalar_one_or_none()
    if phase_id is None:
        return

    # Deja hueco para intercalar las nuevas etapas sin reescribir el orden actual.
    connection.execute(
        sa.text("UPDATE tracking_stage_templates SET sort_order = sort_order * 10 WHERE phase_id = :phase_id"),
        {"phase_id": phase_id},
    )
    connection.execute(
        sa.text("UPDATE opportunity_tracking_stages SET sort_order = sort_order * 10 WHERE phase_id = :phase_id"),
        {"phase_id": phase_id},
    )

    new_template_ids: dict[str, int] = {}
    for stage in INFORMATIONAL_STAGES:
        template_id = connection.execute(
            sa.text(
                "INSERT INTO tracking_stage_templates "
                "(phase_id, name, sort_order, is_active, is_outcome_step, is_informational, created_at, updated_at) "
                "VALUES (:phase_id, :name, :sort_order, true, false, true, :now, :now) "
                "RETURNING id"
            ),
            {"phase_id": phase_id, "name": stage["name"], "sort_order": stage["sort_order"], "now": now},
        ).scalar_one()
        new_template_ids[stage["name"]] = template_id

    tracking_ids = [
        row.tracking_id
        for row in connection.execute(
            sa.text("SELECT DISTINCT tracking_id FROM opportunity_tracking_stages WHERE phase_id = :phase_id"),
            {"phase_id": phase_id},
        )
    ]
    for tracking_id in tracking_ids:
        for stage in INFORMATIONAL_STAGES:
            connection.execute(
                sa.text(
                    "INSERT INTO opportunity_tracking_stages "
                    "(tracking_id, phase_id, stage_template_id, name, sort_order, is_outcome_step, "
                    "is_informational, due_date, completed, status, outcome, created_at, updated_at) "
                    "VALUES (:tracking_id, :phase_id, :template_id, :name, :sort_order, false, "
                    "true, NULL, false, 'pendiente', '', :now, :now)"
                ),
                {
                    "tracking_id": tracking_id,
                    "phase_id": phase_id,
                    "template_id": new_template_ids[stage["name"]],
                    "name": stage["name"],
                    "sort_order": stage["sort_order"],
                    "now": now,
                },
            )


def downgrade() -> None:
    connection = op.get_bind()
    phase_id = connection.execute(
        sa.text("SELECT id FROM tracking_phases WHERE country = 'peru' AND key = 'cotizacion'")
    ).scalar_one_or_none()
    if phase_id is not None:
        connection.execute(
            sa.text("DELETE FROM opportunity_tracking_stages WHERE phase_id = :phase_id AND is_informational = true"),
            {"phase_id": phase_id},
        )
        connection.execute(
            sa.text("DELETE FROM tracking_stage_templates WHERE phase_id = :phase_id AND is_informational = true"),
            {"phase_id": phase_id},
        )
        connection.execute(
            sa.text("UPDATE tracking_stage_templates SET sort_order = sort_order / 10 WHERE phase_id = :phase_id"),
            {"phase_id": phase_id},
        )
        connection.execute(
            sa.text("UPDATE opportunity_tracking_stages SET sort_order = sort_order / 10 WHERE phase_id = :phase_id"),
            {"phase_id": phase_id},
        )

    op.drop_column("opportunity_tracking_stages", "is_informational")
    op.drop_column("tracking_stage_templates", "is_informational")
