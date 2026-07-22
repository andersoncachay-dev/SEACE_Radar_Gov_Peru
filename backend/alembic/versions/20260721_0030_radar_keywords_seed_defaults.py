from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "20260721_0030"
down_revision = "20260721_0029"
branch_labels = None
depends_on = None

# The radar's six "base" keywords used to be hardcoded in DEFAULT_RADAR_KEYWORDS
# and could never be edited or removed by admins. Seeding them here as normal
# radar_keywords rows (created_by_id NULL) makes them behave exactly like any
# other keyword: editable, removable, re-addable — no more protected words.

DEFAULT_KEYWORDS = ("satelital", "internet", "conectividad", "LEO", "GEO", "órbita")
COUNTRIES = ("peru", "chile")


def _normalize(value: str) -> str:
    plain = unicodedata.normalize("NFD", value.strip().lower())
    plain = "".join(char for char in plain if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", plain)


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    radar_keywords = sa.Table("radar_keywords", metadata, autoload_with=bind)
    now = datetime.utcnow()
    for country in COUNTRIES:
        for keyword in DEFAULT_KEYWORDS:
            normalized = _normalize(keyword)
            exists = bind.execute(
                sa.select(radar_keywords.c.id).where(
                    radar_keywords.c.country == country,
                    radar_keywords.c.normalized_keyword == normalized,
                )
            ).first()
            if exists:
                continue
            bind.execute(
                radar_keywords.insert().values(
                    country=country,
                    keyword=keyword,
                    normalized_keyword=normalized,
                    created_by_id=None,
                    created_at=now,
                    updated_at=now,
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    radar_keywords = sa.Table("radar_keywords", metadata, autoload_with=bind)
    for country in COUNTRIES:
        for keyword in DEFAULT_KEYWORDS:
            bind.execute(
                radar_keywords.delete().where(
                    radar_keywords.c.country == country,
                    radar_keywords.c.normalized_keyword == _normalize(keyword),
                    radar_keywords.c.created_by_id.is_(None),
                )
            )
