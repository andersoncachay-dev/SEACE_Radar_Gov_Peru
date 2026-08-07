from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from datetime import datetime
import re
import unicodedata

revision = "20260805_0033"
down_revision = "20260722_0032"
branch_labels = None
depends_on = None

ARGENTINA_DEFAULT_KEYWORDS = ("satelital", "internet", "conectividad", "LEO", "GEO", "órbita")


def _normalize_keyword(value: str) -> str:
    plain = unicodedata.normalize("NFD", value.strip().lower())
    plain = "".join(char for char in plain if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", plain)


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("phone_argentina", sa.String(length=32), nullable=False, server_default=""),
    )
    op.add_column(
        "opportunities",
        sa.Column("record_type", sa.String(length=40), nullable=False, server_default="proceso"),
    )
    op.add_column(
        "opportunities",
        sa.Column("expediente", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "opportunities",
        sa.Column("contracting_unit", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "opportunities",
        sa.Column("financial_service", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column("opportunities", sa.Column("opening_date", sa.DateTime(), nullable=True))

    # Argentina starts with the same commercial workflow used by Chile. The
    # templates remain country-specific, so administrators can adapt them later
    # without changing existing Peru/Chile tracking instances.
    connection = op.get_bind()
    now = datetime.utcnow()
    metadata = sa.MetaData()
    radar_keywords = sa.Table("radar_keywords", metadata, autoload_with=connection)
    for keyword in ARGENTINA_DEFAULT_KEYWORDS:
        normalized_keyword = _normalize_keyword(keyword)
        exists = connection.execute(
            sa.select(radar_keywords.c.id).where(
                radar_keywords.c.country == "argentina",
                radar_keywords.c.normalized_keyword == normalized_keyword,
            )
        ).first()
        if not exists:
            connection.execute(
                radar_keywords.insert().values(
                    country="argentina",
                    keyword=keyword,
                    normalized_keyword=normalized_keyword,
                    created_by_id=None,
                    created_at=now,
                    updated_at=now,
                )
            )
    chile_phases = list(
        connection.execute(
            sa.text(
                "SELECT id, key, name, sort_order, is_active "
                "FROM tracking_phases WHERE country = 'chile' ORDER BY sort_order"
            )
        )
    )
    for phase in chile_phases:
        argentina_phase_id = connection.execute(
            sa.text(
                "INSERT INTO tracking_phases "
                "(country, key, name, sort_order, is_active, created_at, updated_at) "
                "VALUES ('argentina', :key, :name, :sort_order, :is_active, :now, :now) RETURNING id"
            ),
            {
                "key": phase.key,
                "name": phase.name,
                "sort_order": phase.sort_order,
                "is_active": phase.is_active,
                "now": now,
            },
        ).scalar_one()
        templates = list(
            connection.execute(
                sa.text(
                    "SELECT id, name, sort_order, is_active, is_outcome_step, is_informational, "
                    "default_duration_days FROM tracking_stage_templates WHERE phase_id = :phase_id"
                ),
                {"phase_id": phase.id},
            )
        )
        for template in templates:
            argentina_template_id = connection.execute(
                sa.text(
                    "INSERT INTO tracking_stage_templates "
                    "(phase_id, name, sort_order, is_active, is_outcome_step, is_informational, "
                    "default_duration_days, created_at, updated_at) VALUES "
                    "(:phase_id, :name, :sort_order, :is_active, :is_outcome_step, :is_informational, "
                    ":default_duration_days, :now, :now) RETURNING id"
                ),
                {
                    "phase_id": argentina_phase_id,
                    "name": template.name,
                    "sort_order": template.sort_order,
                    "is_active": template.is_active,
                    "is_outcome_step": template.is_outcome_step,
                    "is_informational": template.is_informational,
                    "default_duration_days": template.default_duration_days,
                    "now": now,
                },
            ).scalar_one()
            connection.execute(
                sa.text(
                    "INSERT INTO tracking_stage_template_areas "
                    "(stage_template_id, area_id, created_at, updated_at) "
                    "SELECT :new_template_id, area_id, :now, :now "
                    "FROM tracking_stage_template_areas WHERE stage_template_id = :source_template_id"
                ),
                {
                    "new_template_id": argentina_template_id,
                    "source_template_id": template.id,
                    "now": now,
                },
            )


def downgrade() -> None:
    connection = op.get_bind()
    metadata = sa.MetaData()
    radar_keywords = sa.Table("radar_keywords", metadata, autoload_with=connection)
    for keyword in ARGENTINA_DEFAULT_KEYWORDS:
        connection.execute(
            radar_keywords.delete().where(
                radar_keywords.c.country == "argentina",
                radar_keywords.c.normalized_keyword == _normalize_keyword(keyword),
                radar_keywords.c.created_by_id.is_(None),
            )
        )
    connection.execute(
        sa.text(
            "DELETE FROM tracking_stage_template_areas WHERE stage_template_id IN ("
            "SELECT tst.id FROM tracking_stage_templates tst "
            "JOIN tracking_phases tp ON tp.id = tst.phase_id WHERE tp.country = 'argentina')"
        )
    )
    connection.execute(
        sa.text(
            "DELETE FROM tracking_stage_templates WHERE phase_id IN "
            "(SELECT id FROM tracking_phases WHERE country = 'argentina')"
        )
    )
    connection.execute(sa.text("DELETE FROM tracking_phases WHERE country = 'argentina'"))
    op.drop_column("users", "phone_argentina")
    op.drop_column("opportunities", "opening_date")
    op.drop_column("opportunities", "financial_service")
    op.drop_column("opportunities", "contracting_unit")
    op.drop_column("opportunities", "expediente")
    op.drop_column("opportunities", "record_type")
