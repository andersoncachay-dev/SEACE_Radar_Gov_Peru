from __future__ import annotations

import json
import os

from .services.scheduler_service import enqueue_active_profiles


def main() -> None:
    country = os.getenv("INGESTION_COUNTRY", "").strip().lower() or None
    summary = enqueue_active_profiles(country=country)
    print(json.dumps({"country": country or "all", **summary}, ensure_ascii=False))
    if summary["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
