from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "20260720_0020"
down_revision = "20260717_0019"
branch_labels = None
depends_on = None


AREAS = [
    {"key": "comercial", "name": "Comercial", "sort_order": 1},
    {"key": "analisis_bi", "name": "Análisis/BI", "sort_order": 2},
    {"key": "preventa", "name": "Preventa", "sort_order": 3},
    {"key": "finanzas", "name": "Finanzas", "sort_order": 4},
    {"key": "operaciones", "name": "Operaciones", "sort_order": 5},
]

RESPONSIBLES = [
    {"full_name": "Rodrigo Rejas", "email": "rodrigo.rejas@rodarconsulting.com", "country_scope": "chile", "areas": ["comercial"]},
    {"full_name": "Anderson Cachay", "email": "anderson.cachay@rodarconsulting.com", "country_scope": "peru", "areas": ["comercial"]},
    {"full_name": "Angello Quintero", "email": "angello.quintero@rodarconsulting.com", "country_scope": "ambos", "areas": ["analisis_bi"]},
    {"full_name": "Juan Asto", "email": "juan.asto@rodarconsulting.com", "country_scope": "ambos", "areas": ["preventa"]},
    {"full_name": "Cristobal Saenz", "email": "cristobal.saenz@rodarconsulting.com", "country_scope": "chile", "areas": ["finanzas"]},
    {"full_name": "Mariella Mendoza", "email": "mariella.mendoza@rodarconsulting.com", "country_scope": "peru", "areas": ["finanzas"]},
    {"full_name": "Luis Eyzaguirre", "email": "luis.eyzaguirre@rodarconsulting.com", "country_scope": "ambos", "areas": ["operaciones"]},
]


def upgrade() -> None:
    op.create_table(
        "tracking_areas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index(op.f("ix_tracking_areas_key"), "tracking_areas", ["key"], unique=True)

    op.create_table(
        "tracking_responsibles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("country_scope", sa.String(length=10), nullable=False, server_default="ambos"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "tracking_area_responsibles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("area_id", sa.Integer(), nullable=False),
        sa.Column("responsible_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["area_id"], ["tracking_areas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["responsible_id"], ["tracking_responsibles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("area_id", "responsible_id", name="uq_tracking_area_responsible"),
    )
    op.create_index(op.f("ix_tracking_area_responsibles_area_id"), "tracking_area_responsibles", ["area_id"], unique=False)
    op.create_index(op.f("ix_tracking_area_responsibles_responsible_id"), "tracking_area_responsibles", ["responsible_id"], unique=False)

    now = datetime.utcnow()

    areas_table = sa.table(
        "tracking_areas",
        sa.column("id", sa.Integer()),
        sa.column("key", sa.String()),
        sa.column("name", sa.String()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    op.bulk_insert(
        areas_table,
        [
            {**area, "is_active": True, "created_at": now, "updated_at": now}
            for area in AREAS
        ],
    )

    connection = op.get_bind()
    area_ids = {
        row.key: row.id
        for row in connection.execute(sa.text("SELECT id, key FROM tracking_areas"))
    }

    responsibles_table = sa.table(
        "tracking_responsibles",
        sa.column("id", sa.Integer()),
        sa.column("full_name", sa.String()),
        sa.column("email", sa.String()),
        sa.column("country_scope", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    op.bulk_insert(
        responsibles_table,
        [
            {
                "full_name": r["full_name"],
                "email": r["email"],
                "country_scope": r["country_scope"],
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            for r in RESPONSIBLES
        ],
    )

    responsible_ids = {
        row.full_name: row.id
        for row in connection.execute(sa.text("SELECT id, full_name FROM tracking_responsibles"))
    }

    join_rows = []
    for r in RESPONSIBLES:
        for area_key in r["areas"]:
            join_rows.append(
                {
                    "area_id": area_ids[area_key],
                    "responsible_id": responsible_ids[r["full_name"]],
                    "created_at": now,
                    "updated_at": now,
                }
            )

    join_table = sa.table(
        "tracking_area_responsibles",
        sa.column("area_id", sa.Integer()),
        sa.column("responsible_id", sa.Integer()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    op.bulk_insert(join_table, join_rows)


def downgrade() -> None:
    op.drop_index(op.f("ix_tracking_area_responsibles_responsible_id"), table_name="tracking_area_responsibles")
    op.drop_index(op.f("ix_tracking_area_responsibles_area_id"), table_name="tracking_area_responsibles")
    op.drop_table("tracking_area_responsibles")
    op.drop_table("tracking_responsibles")
    op.drop_index(op.f("ix_tracking_areas_key"), table_name="tracking_areas")
    op.drop_table("tracking_areas")
