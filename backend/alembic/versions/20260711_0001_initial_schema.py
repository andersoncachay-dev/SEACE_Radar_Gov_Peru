from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260711_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "search_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=False, server_default="satelital"),
        sa.Column("source", sa.String(length=80), nullable=False, server_default="seace_public_browser"),
        sa.Column("year", sa.String(length=10), nullable=False, server_default="2026"),
        sa.Column("version", sa.String(length=40), nullable=False, server_default="Seace 3"),
        sa.Column("max_results", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("search_profile_id", sa.Integer(), sa.ForeignKey("search_profiles.id"), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("rows_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("diagnostics", sa.Text(), nullable=False, server_default=""),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "opportunities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("external_id", sa.String(length=180), nullable=False),
        sa.Column("entity", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("nomenclature", sa.String(length=180), nullable=False, server_default=""),
        sa.Column("object_type", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("region", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("priority", sa.String(length=10), nullable=False, server_default="C"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reasons", sa.Text(), nullable=False, server_default=""),
        sa.Column("detail_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("requirement_pdf_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("requirement_pdf_local", sa.Text(), nullable=False, server_default=""),
        sa.Column("publication_date", sa.DateTime(), nullable=True),
        sa.Column("consultation_deadline", sa.DateTime(), nullable=True),
        sa.Column("quote_deadline", sa.DateTime(), nullable=True),
        sa.Column("proposal_deadline", sa.DateTime(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("source", "external_id", name="uq_opportunities_source_external_id"),
    )

    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False, server_default="email"),
        sa.Column("destination", sa.String(length=255), nullable=False),
        sa.Column("min_priority", sa.String(length=10), nullable=False, server_default="A"),
        sa.Column("hours_before_deadline", sa.Integer(), nullable=False, server_default="48"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "opportunity_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("opportunity_id", sa.Integer(), sa.ForeignKey("opportunities.id"), nullable=False),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("scrape_runs.id"), nullable=True),
        sa.Column("previous_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("change_type", sa.String(length=40), nullable=False, server_default="upsert"),
        sa.Column("raw_payload", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("opportunity_id", sa.Integer(), sa.ForeignKey("opportunities.id"), nullable=False),
        sa.Column("rule_id", sa.Integer(), sa.ForeignKey("alert_rules.id"), nullable=False),
        sa.Column("alert_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("opportunity_id", "rule_id", "alert_type", name="uq_alert_once"),
    )


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("opportunity_snapshots")
    op.drop_table("alert_rules")
    op.drop_table("opportunities")
    op.drop_table("scrape_runs")
    op.drop_table("search_profiles")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
