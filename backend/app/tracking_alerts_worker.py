from __future__ import annotations

import json
import os

from .database import SessionLocal
from .services.scheduler_service import claim_tracking_time_alerts_run
from .services.tracking_service import evaluate_time_status_alerts


def main() -> None:
    force_run = os.getenv("TRACKING_ALERTS_FORCE", "false").strip().lower() in {"1", "true", "yes"}
    if not force_run:
        should_run, next_update_at = claim_tracking_time_alerts_run()
        if not should_run:
            print(json.dumps({"skipped": True, "next_update_at": next_update_at.isoformat()}, ensure_ascii=False))
            return
    db = SessionLocal()
    try:
        summary = evaluate_time_status_alerts(db)
    finally:
        db.close()
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
