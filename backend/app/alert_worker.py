from __future__ import annotations

import json

from .database import SessionLocal
from .services.notification_service import evaluate_alerts, send_pending_alerts


def main() -> None:
    db = SessionLocal()
    try:
        created = evaluate_alerts(db)
        processed = send_pending_alerts(db)
        summary = {
            "created": len(created),
            "processed": len(processed),
            "sent": sum(1 for item in processed if item.status == "sent"),
            "retrying": sum(1 for item in processed if item.status == "retrying"),
            "failed": sum(1 for item in processed if item.status == "failed"),
        }
        print(json.dumps(summary, ensure_ascii=False))
    finally:
        db.close()


if __name__ == "__main__":
    main()
