from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "20260721_0024"
down_revision = "20260720_0023"
branch_labels = None
depends_on = None

# Perú y Chile pueden tener etapas distintas dentro de cada fase, así que las
# fases (y sus plantillas de etapas) dejan de ser globales y pasan a ser por
# país. Las filas existentes (creadas compartidas) se quedan como "peru" y se
# clonan como punto de partida editable para "chile" — el admin las ajusta
# luego desde "Gestionar Responsables".
#
# Nota: esta migración no remapea trackings ya iniciados para oportunidades de
# Chile bajo el modelo anterior (compartido) porque el módulo se lanzó el
# mismo día que este cambio y no hay datos reales de producción todavía.

PHASES_TABLE = sa.table(
    "tracking_phases",
    sa.column("id", sa.Integer()),
    sa.column("key", sa.String()),
    sa.column("name", sa.String()),
    sa.column("sort_order", sa.Integer()),
    sa.column("country", sa.String()),
    sa.column("is_active", sa.Boolean()),
    sa.column("created_at", sa.DateTime()),
    sa.column("updated_at", sa.DateTime()),
)

STAGE_TEMPLATES_TABLE = sa.table(
    "tracking_stage_templates",
    sa.column("id", sa.Integer()),
    sa.column("phase_id", sa.Integer()),
    sa.column("name", sa.String()),
    sa.column("sort_order", sa.Integer()),
    sa.column("is_active", sa.Boolean()),
    sa.column("is_outcome_step", sa.Boolean()),
    sa.column("default_duration_days", sa.Integer()),
    sa.column("created_at", sa.DateTime()),
    sa.column("updated_at", sa.DateTime()),
)

STAGE_TEMPLATE_AREAS_TABLE = sa.table(
    "tracking_stage_template_areas",
    sa.column("stage_template_id", sa.Integer()),
    sa.column("area_id", sa.Integer()),
    sa.column("created_at", sa.DateTime()),
    sa.column("updated_at", sa.DateTime()),
)


def upgrade() -> None:
    op.add_column("tracking_phases", sa.Column("country", sa.String(length=10), nullable=False, server_default="peru"))
    op.drop_constraint("tracking_phases_key_key", "tracking_phases", type_="unique")
    op.drop_index("ix_tracking_phases_key", table_name="tracking_phases")
    op.create_index(op.f("ix_tracking_phases_country_key"), "tracking_phases", ["country", "key"], unique=True)

    connection = op.get_bind()
    now = datetime.utcnow()

    peru_phases = list(
        connection.execute(sa.text("SELECT id, key, name, sort_order FROM tracking_phases WHERE country = 'peru' ORDER BY sort_order"))
    )
    peru_templates = list(
        connection.execute(
            sa.text(
                "SELECT id, phase_id, name, sort_order, is_active, is_outcome_step, default_duration_days "
                "FROM tracking_stage_templates ORDER BY sort_order"
            )
        )
    )
    template_area_ids_by_template_id: dict[int, list[int]] = {}
    for row in connection.execute(sa.text("SELECT stage_template_id, area_id FROM tracking_stage_template_areas")):
        template_area_ids_by_template_id.setdefault(row.stage_template_id, []).append(row.area_id)

    for phase in peru_phases:
        new_phase_id = connection.execute(
            sa.insert(PHASES_TABLE)
            .values(key=phase.key, name=phase.name, sort_order=phase.sort_order, country="chile", is_active=True, created_at=now, updated_at=now)
            .returning(PHASES_TABLE.c.id)
        ).scalar_one()

        for template in (t for t in peru_templates if t.phase_id == phase.id):
            new_template_id = connection.execute(
                sa.insert(STAGE_TEMPLATES_TABLE)
                .values(
                    phase_id=new_phase_id,
                    name=template.name,
                    sort_order=template.sort_order,
                    is_active=template.is_active,
                    is_outcome_step=template.is_outcome_step,
                    default_duration_days=template.default_duration_days,
                    created_at=now,
                    updated_at=now,
                )
                .returning(STAGE_TEMPLATES_TABLE.c.id)
            ).scalar_one()

            area_ids = template_area_ids_by_template_id.get(template.id, [])
            if area_ids:
                connection.execute(
                    sa.insert(STAGE_TEMPLATE_AREAS_TABLE),
                    [{"stage_template_id": new_template_id, "area_id": area_id, "created_at": now, "updated_at": now} for area_id in area_ids],
                )


def downgrade() -> None:
    connection = op.get_bind()
    chile_phase_ids = [row.id for row in connection.execute(sa.text("SELECT id FROM tracking_phases WHERE country = 'chile'"))]
    if chile_phase_ids:
        connection.execute(
            sa.text(
                "DELETE FROM tracking_stage_template_areas WHERE stage_template_id IN "
                "(SELECT id FROM tracking_stage_templates WHERE phase_id = ANY(:phase_ids))"
            ),
            {"phase_ids": chile_phase_ids},
        )
        connection.execute(
            sa.text("DELETE FROM tracking_stage_templates WHERE phase_id = ANY(:phase_ids)"),
            {"phase_ids": chile_phase_ids},
        )
        connection.execute(sa.text("DELETE FROM tracking_phases WHERE id = ANY(:phase_ids)"), {"phase_ids": chile_phase_ids})

    op.drop_index(op.f("ix_tracking_phases_country_key"), table_name="tracking_phases")
    op.create_index("ix_tracking_phases_key", "tracking_phases", ["key"], unique=True)
    op.create_unique_constraint("tracking_phases_key_key", "tracking_phases", ["key"])
    op.drop_column("tracking_phases", "country")
