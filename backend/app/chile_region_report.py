from __future__ import annotations

import json
import os

from sqlalchemy import func, or_, select

from .database import SessionLocal
from .models import Opportunity


def main() -> None:
    db = SessionLocal()
    try:
        base = (Opportunity.source.like("mercado_publico%"), Opportunity.is_archived.is_(False))
        missing = db.scalar(
            select(func.count()).select_from(Opportunity).where(
                *base,
                or_(func.trim(Opportunity.region) == "", func.lower(func.trim(Opportunity.region)) == "chile"),
            )
        )
        total = db.scalar(select(func.count()).select_from(Opportunity).where(*base))
        missing_items = db.execute(
            select(Opportunity.id, Opportunity.external_id, Opportunity.entity)
            .where(
                *base,
                or_(func.trim(Opportunity.region) == "", func.lower(func.trim(Opportunity.region)) == "chile"),
            )
            .order_by(Opportunity.id)
        ).all()
        distribution_rows = db.execute(
            select(Opportunity.region, func.count())
            .where(*base)
            .group_by(Opportunity.region)
            .order_by(func.count().desc())
        ).all()
        distribution = [[region, count] for region, count in distribution_rows]
        print(json.dumps({
            "total": total,
            "missing": missing,
            "missing_items": [[item.id, item.external_id, item.entity] for item in missing_items],
            "distribution": distribution,
        }, ensure_ascii=False))
        max_missing = int(os.getenv("MAX_MISSING", "0"))
        if missing > max_missing:
            raise SystemExit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
