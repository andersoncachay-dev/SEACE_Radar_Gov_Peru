from __future__ import annotations

import json
import os

from .services.scheduler_service import claim_external_scheduler_run, enqueue_active_profiles


def main() -> None:
    country = os.getenv("INGESTION_COUNTRY", "").strip().lower() or None
    force_run = os.getenv("INGESTION_FORCE", "false").strip().lower() in {"1", "true", "yes"}
    if country and not force_run:
        should_run, next_update_at = claim_external_scheduler_run(country)
        if not should_run:
            print(json.dumps({"country": country, "skipped": True, "next_update_at": next_update_at.isoformat()}, ensure_ascii=False))
            return
    summary = enqueue_active_profiles(country=country)
    print(json.dumps({"country": country or "all", "forced": force_run, **summary}, ensure_ascii=False))
    if summary["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
