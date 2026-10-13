from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261012_0035"
down_revision = "20260902_0034"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    ]


def _str(name: str, length: int, **kwargs) -> sa.Column:
    return sa.Column(name, sa.String(length=length), nullable=False, server_default="", **kwargs)


def _text(name: str) -> sa.Column:
    return sa.Column(name, sa.Text(), nullable=False, server_default="")


def _float(name: str) -> sa.Column:
    return sa.Column(name, sa.Float(), nullable=False, server_default="0")


def upgrade() -> None:
    op.add_column("users", sa.Column("module_access", sa.String(length=80), nullable=False, server_default="radar"))
    op.add_column("users", sa.Column("historico_digest", sa.Boolean(), nullable=False, server_default=sa.false()))
    # Admins get every module (they run imports); everyone else keeps today's
    # behaviour (the live radar only) until an admin grants Histórico Perú.
    op.execute("UPDATE users SET module_access = 'radar,historico_peru' WHERE role = 'admin'")

    op.create_table(
        "hist_import_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        _str("origin", 30),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued", index=True),
        sa.Column("triggered_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("data_cut_date", sa.Date(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        _text("message"),
        sa.Column("files_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("counts_json", sa.Text(), nullable=False, server_default="{}"),
        _text("error"),
        *_timestamps(),
    )

    op.create_table(
        "hist_keywords",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keyword", sa.String(length=120), nullable=False, unique=True),
        sa.Column("category", sa.String(length=80), nullable=False, server_default="Internet (sin especificar)"),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="include"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
    )

    op.create_table(
        "hist_entities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ruc", sa.String(length=20), nullable=False, unique=True, index=True),
        _str("code", 20, index=True),
        _str("name", 300),
        _str("entity_type", 80),
        _str("government_level", 40),
        _str("department", 80),
        _str("province", 80),
        _str("district", 80),
        *_timestamps(),
    )

    op.create_table(
        "hist_contractings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset", sa.String(length=20), nullable=False),
        sa.Column("source_key", sa.String(length=120), nullable=False),
        _str("source_period", 7, index=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=True, index=True),
        _str("process_group", 60, index=True),
        _str("procedure", 160),
        _str("nomenclature", 200, index=True),
        _str("convocatoria_code", 30, index=True),
        _str("item_number", 20),
        _str("entity_code", 20, index=True),
        _str("entity_ruc", 20, index=True),
        _str("entity_name", 300),
        _str("department", 80, index=True),
        _text("description"),
        _str("category", 80, index=True),
        _float("amount"),
        _float("reference_amount"),
        _str("supplier_ruc", 20, index=True),
        _str("supplier_name", 300),
        _str("status", 60),
        _str("direct_cause", 200),
        _str("object_type", 40),
        _str("government_level", 40, index=True),
        sa.Column("relevance", sa.String(length=30), nullable=False, server_default="ok", index=True),
        sa.Column("import_run_id", sa.Integer(), sa.ForeignKey("hist_import_runs.id", ondelete="SET NULL"), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("dataset", "source_key", name="uq_hist_contracting_source"),
    )
    op.create_index("ix_hist_contracting_period", "hist_contractings", ["year", "month"])

    op.create_table(
        "hist_contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contract_code", sa.String(length=40), nullable=False, unique=True),
        _str("entity_code", 20),
        _str("convocatoria_code", 30),
        _str("item_number", 20),
        _str("contract_number", 200),
        _float("amount_item"),
        _float("amount_additional"),
        _float("amount_reduction"),
        _float("amount_extension"),
        _float("amount_complementary"),
        _str("contractor_ruc", 20),
        _text("url"),
        sa.Column("signed_at", sa.Date(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("end_date_updated", sa.Date(), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_hist_contract_item", "hist_contracts", ["entity_code", "convocatoria_code", "item_number"])

    op.create_table(
        "hist_expirings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contracting_id", sa.Integer(), sa.ForeignKey("hist_contractings.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("hist_contracts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=False, index=True),
        _str("date_source", 80),
        sa.Column("is_real_date", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("days_to_end", sa.Integer(), nullable=False, server_default="0"),
        _str("bucket", 30, index=True),
        _float("monthly_amount"),
        _float("extras_amount"),
        sa.Column("possibly_renewed", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
    )

    op.create_table(
        "hist_recurrings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_ruc", sa.String(length=20), nullable=False),
        _str("entity_name", 300),
        _str("department", 80, index=True),
        _str("government_level", 40),
        sa.Column("supplier_ruc", sa.String(length=20), nullable=False),
        _str("supplier_name", 300),
        _str("category", 80),
        sa.Column("orders_12m", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("months_12m", sa.Integer(), nullable=False, server_default="0"),
        _float("amount_12m_supplier"),
        _float("amount_12m_entity"),
        sa.Column("suppliers_12m", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_order_date", sa.Date(), nullable=True),
        _float("last_order_amount"),
        _text("last_order_description"),
        sa.Column("last_order_id", sa.Integer(), sa.ForeignKey("hist_contractings.id", ondelete="SET NULL"), nullable=True),
        _str("pattern", 40),
        sa.Column("next_purchase_date", sa.Date(), nullable=True, index=True),
        sa.Column("days_to_next", sa.Integer(), nullable=False, server_default="0"),
        _str("bucket", 30, index=True),
        *_timestamps(),
        sa.UniqueConstraint("entity_ruc", "supplier_ruc", name="uq_hist_recurring_pair"),
    )

    op.create_table(
        "hist_pac_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False, index=True),
        _str("entity_code", 20),
        _str("entity_ruc", 20, index=True),
        _str("entity_name", 300),
        _str("department", 80, index=True),
        _str("government_level", 40),
        _str("version", 20),
        _str("reference_number", 30),
        _text("process_description"),
        _str("process_type", 160),
        _str("process_group", 60),
        _str("object_type", 40),
        _str("item_number", 20),
        _text("item_description"),
        _str("category", 80),
        _float("quantity"),
        _str("unit", 80),
        _str("item_department", 80),
        _str("province", 80),
        _str("district", 120),
        sa.Column("planned_month", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_at", sa.Date(), nullable=True),
        _str("situation", 60, index=True),
        sa.Column("already_awarded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("relevance", sa.String(length=30), nullable=False, server_default="ok"),
        *_timestamps(),
        sa.UniqueConstraint("year", "entity_code", "reference_number", "item_number", name="uq_hist_pac_item"),
    )

    op.create_table(
        "hist_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("ref_key", sa.String(length=160), nullable=False),
        sa.Column("expiring_id", sa.Integer(), sa.ForeignKey("hist_expirings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recurring_id", sa.Integer(), sa.ForeignKey("hist_recurrings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("pac_item_id", sa.Integer(), sa.ForeignKey("hist_pac_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("priority", sa.String(length=4), nullable=False, server_default="P4", index=True),
        _float("score"),
        _str("title", 300),
        _text("detail"),
        _str("entity_name", 300),
        _str("department", 80),
        _float("amount"),
        sa.Column("due_date", sa.Date(), nullable=True, index=True),
        _str("category", 80, index=True),
        _str("process_group", 60),
        _str("government_level", 40),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="nueva", index=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true(), index=True),
        sa.Column("assignee_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("dismissed_due_date", sa.Date(), nullable=True),
        sa.Column("first_seen_import_id", sa.Integer(), sa.ForeignKey("hist_import_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_evaluated_at", sa.DateTime(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("kind", "ref_key", name="uq_hist_alert_ref"),
    )

    op.create_table(
        "hist_alert_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        _str("kinds", 80),
        _text("categories"),
        _text("departments"),
        _str("government_levels", 200),
        _text("process_groups"),
        _text("keywords"),
        _float("min_amount"),
        sa.Column("min_priority", sa.String(length=4), nullable=False, server_default="P4"),
        *_timestamps(),
    )


def downgrade() -> None:
    for table in (
        "hist_alert_preferences",
        "hist_alerts",
        "hist_pac_items",
        "hist_recurrings",
        "hist_expirings",
        "hist_contracts",
        "hist_contractings",
        "hist_entities",
        "hist_keywords",
        "hist_import_runs",
    ):
        op.drop_table(table)
    op.drop_column("users", "historico_digest")
    op.drop_column("users", "module_access")
