from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260720_0022"
down_revision = "20260720_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunity_trackings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("current_phase_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("quotation_outcome", sa.String(length=10), nullable=False, server_default="pendiente"),
        sa.Column("quotation_outcome_at", sa.DateTime(), nullable=True),
        sa.Column("quotation_outcome_by_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("started_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["current_phase_id"], ["tracking_phases.id"]),
        sa.ForeignKeyConstraint(["quotation_outcome_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["started_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("opportunity_id"),
    )
    op.create_index(op.f("ix_opportunity_trackings_opportunity_id"), "opportunity_trackings", ["opportunity_id"], unique=True)

    op.create_table(
        "opportunity_tracking_stages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tracking_id", sa.Integer(), nullable=False),
        sa.Column("phase_id", sa.Integer(), nullable=False),
        sa.Column("stage_template_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_outcome_step", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_by_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pendiente"),
        sa.Column("outcome", sa.String(length=10), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tracking_id"], ["opportunity_trackings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["phase_id"], ["tracking_phases.id"]),
        sa.ForeignKeyConstraint(["stage_template_id"], ["tracking_stage_templates.id"]),
        sa.ForeignKeyConstraint(["completed_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_opportunity_tracking_stages_tracking_id"), "opportunity_tracking_stages", ["tracking_id"], unique=False)
    op.create_index(op.f("ix_opportunity_tracking_stages_completed"), "opportunity_tracking_stages", ["completed"], unique=False)

    op.create_table(
        "opportunity_tracking_stage_areas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stage_id", sa.Integer(), nullable=False),
        sa.Column("area_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["stage_id"], ["opportunity_tracking_stages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["area_id"], ["tracking_areas.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stage_id", "area_id", name="uq_tracking_stage_area"),
    )
    op.create_index(op.f("ix_opportunity_tracking_stage_areas_stage_id"), "opportunity_tracking_stage_areas", ["stage_id"], unique=False)

    op.create_table(
        "opportunity_tracking_stage_assignees",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stage_id", sa.Integer(), nullable=False),
        sa.Column("responsible_id", sa.Integer(), nullable=False),
        sa.Column("area_id", sa.Integer(), nullable=True),
        sa.Column("assigned_by_id", sa.Integer(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notification_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("notification_sent_at", sa.DateTime(), nullable=True),
        sa.Column("notification_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["stage_id"], ["opportunity_tracking_stages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["responsible_id"], ["tracking_responsibles.id"]),
        sa.ForeignKeyConstraint(["area_id"], ["tracking_areas.id"]),
        sa.ForeignKeyConstraint(["assigned_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stage_id", "responsible_id", name="uq_tracking_stage_assignee"),
    )
    op.create_index(op.f("ix_opportunity_tracking_stage_assignees_stage_id"), "opportunity_tracking_stage_assignees", ["stage_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_opportunity_tracking_stage_assignees_stage_id"), table_name="opportunity_tracking_stage_assignees")
    op.drop_table("opportunity_tracking_stage_assignees")
    op.drop_index(op.f("ix_opportunity_tracking_stage_areas_stage_id"), table_name="opportunity_tracking_stage_areas")
    op.drop_table("opportunity_tracking_stage_areas")
    op.drop_index(op.f("ix_opportunity_tracking_stages_completed"), table_name="opportunity_tracking_stages")
    op.drop_index(op.f("ix_opportunity_tracking_stages_tracking_id"), table_name="opportunity_tracking_stages")
    op.drop_table("opportunity_tracking_stages")
    op.drop_index(op.f("ix_opportunity_trackings_opportunity_id"), table_name="opportunity_trackings")
    op.drop_table("opportunity_trackings")
