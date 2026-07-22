from __future__ import annotations

import json
import os

from .database import SessionLocal
from .services.scheduler_service import claim_tracking_date_refresh_run
from .services.tracking_date_refresh_service import refresh_active_opportunity_dates


def main() -> None:
    country = os.getenv("TRACKING_DATE_REFRESH_COUNTRY", "").strip().lower()
    if country not in {"peru", "chile"}:
        raise SystemExit("TRACKING_DATE_REFRESH_COUNTRY debe ser 'peru' o 'chile'")
    force_run = os.getenv("TRACKING_DATE_REFRESH_FORCE", "false").strip().lower() in {"1", "true", "yes"}
    if not force_run:
        should_run, next_update_at = claim_tracking_date_refresh_run(country)
        if not should_run:
            print(json.dumps({"country": country, "skipped": True, "next_update_at": next_update_at.isoformat()}, ensure_ascii=False))
            return
    db = SessionLocal()
    try:
        summary = refresh_active_opportunity_dates(db, country)
    finally:
        db.close()
    print(json.dumps({"country": country, **summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
