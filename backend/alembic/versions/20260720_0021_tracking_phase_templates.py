from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "20260720_0021"
down_revision = "20260720_0020"
branch_labels = None
depends_on = None


PHASES = [
    {"key": "cotizacion", "name": "Cotización", "sort_order": 1},
    {"key": "perfeccionamiento_contrato", "name": "Perfeccionamiento de Contrato", "sort_order": 2},
    {"key": "implementacion", "name": "Implementación", "sort_order": 3},
]

STAGE_TEMPLATES = [
    {
        "phase_key": "cotizacion",
        "name": "Levantamiento de necesidades",
        "sort_order": 1,
        "is_outcome_step": False,
        "areas": ["comercial", "analisis_bi"],
    },
    {
        "phase_key": "cotizacion",
        "name": "Consultas",
        "sort_order": 2,
        "is_outcome_step": False,
        "areas": ["comercial", "preventa"],
    },
    {
        "phase_key": "cotizacion",
        "name": "Cotización",
        "sort_order": 3,
        "is_outcome_step": False,
        "areas": ["comercial", "preventa", "finanzas", "operaciones"],
    },
    {
        "phase_key": "cotizacion",
        "name": "Envío de Propuesta (SEACE / Mercado Público)",
        "sort_order": 4,
        "is_outcome_step": False,
        "areas": ["comercial"],
    },
    {
        "phase_key": "cotizacion",
        "name": "Resultado de la convocatoria",
        "sort_order": 5,
        "is_outcome_step": True,
        "areas": ["comercial"],
    },
    {
        "phase_key": "perfeccionamiento_contrato",
        "name": "Firma de Contrato",
        "sort_order": 1,
        "is_outcome_step": False,
        "areas": ["comercial", "finanzas"],
    },
    {
        "phase_key": "perfeccionamiento_contrato",
        "name": "Garantías/Pólizas",
        "sort_order": 2,
        "is_outcome_step": False,
        "areas": ["finanzas", "operaciones"],
    },
    {
        "phase_key": "perfeccionamiento_contrato",
        "name": "Kickoff Interno",
        "sort_order": 3,
        "is_outcome_step": False,
        "areas": ["operaciones", "comercial"],
    },
    {
        "phase_key": "implementacion",
        "name": "Instalación/Despliegue",
        "sort_order": 1,
        "is_outcome_step": False,
        "areas": ["operaciones"],
    },
    {
        "phase_key": "implementacion",
        "name": "Capacitación",
        "sort_order": 2,
        "is_outcome_step": False,
        "areas": ["operaciones", "preventa"],
    },
    {
        "phase_key": "implementacion",
        "name": "Cierre/Entrega Conforme",
        "sort_order": 3,
        "is_outcome_step": False,
        "areas": ["operaciones", "comercial"],
    },
]


def upgrade() -> None:
    op.create_table(
        "tracking_phases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index(op.f("ix_tracking_phases_key"), "tracking_phases", ["key"], unique=True)

    op.create_table(
        "tracking_stage_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("phase_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_outcome_step", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("default_duration_days", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["phase_id"], ["tracking_phases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tracking_stage_templates_phase_id"), "tracking_stage_templates", ["phase_id"], unique=False)

    op.create_table(
        "tracking_stage_template_areas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stage_template_id", sa.Integer(), nullable=False),
        sa.Column("area_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["stage_template_id"], ["tracking_stage_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["area_id"], ["tracking_areas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stage_template_id", "area_id", name="uq_tracking_stage_template_area"),
    )
    op.create_index(op.f("ix_tracking_stage_template_areas_stage_template_id"), "tracking_stage_template_areas", ["stage_template_id"], unique=False)
    op.create_index(op.f("ix_tracking_stage_template_areas_area_id"), "tracking_stage_template_areas", ["area_id"], unique=False)

    now = datetime.utcnow()
    connection = op.get_bind()

    phases_table = sa.table(
        "tracking_phases",
        sa.column("key", sa.String()),
        sa.column("name", sa.String()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    op.bulk_insert(
        phases_table,
        [{**phase, "is_active": True, "created_at": now, "updated_at": now} for phase in PHASES],
    )

    phase_ids = {row.key: row.id for row in connection.execute(sa.text("SELECT id, key FROM tracking_phases"))}
    area_ids = {row.key: row.id for row in connection.execute(sa.text("SELECT id, key FROM tracking_areas"))}

    stage_templates_table = sa.table(
        "tracking_stage_templates",
        sa.column("phase_id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
        sa.column("is_outcome_step", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    for stage in STAGE_TEMPLATES:
        op.bulk_insert(
            stage_templates_table,
            [
                {
                    "phase_id": phase_ids[stage["phase_key"]],
                    "name": stage["name"],
                    "sort_order": stage["sort_order"],
                    "is_active": True,
                    "is_outcome_step": stage["is_outcome_step"],
                    "created_at": now,
                    "updated_at": now,
                }
            ],
        )

    stage_rows = list(
        connection.execute(sa.text("SELECT id, phase_id, name FROM tracking_stage_templates"))
    )
    stage_areas_table = sa.table(
        "tracking_stage_template_areas",
        sa.column("stage_template_id", sa.Integer()),
        sa.column("area_id", sa.Integer()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    join_rows = []
    for stage in STAGE_TEMPLATES:
        phase_id = phase_ids[stage["phase_key"]]
        stage_row = next(r for r in stage_rows if r.phase_id == phase_id and r.name == stage["name"])
        for area_key in stage["areas"]:
            join_rows.append(
                {
                    "stage_template_id": stage_row.id,
                    "area_id": area_ids[area_key],
                    "created_at": now,
                    "updated_at": now,
                }
            )
    op.bulk_insert(stage_areas_table, join_rows)


def downgrade() -> None:
    op.drop_index(op.f("ix_tracking_stage_template_areas_area_id"), table_name="tracking_stage_template_areas")
    op.drop_index(op.f("ix_tracking_stage_template_areas_stage_template_id"), table_name="tracking_stage_template_areas")
    op.drop_table("tracking_stage_template_areas")
    op.drop_index(op.f("ix_tracking_stage_templates_phase_id"), table_name="tracking_stage_templates")
    op.drop_table("tracking_stage_templates")
    op.drop_index(op.f("ix_tracking_phases_key"), table_name="tracking_phases")
    op.drop_table("tracking_phases")
