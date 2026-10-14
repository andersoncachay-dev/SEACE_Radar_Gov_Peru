"""Entrypoint of the govradar-historico-peru / govradar-historico-chile
Container Apps Jobs (hourly cron). HISTORICO_COUNTRY picks the module
(default peru).

Most invocations exit immediately; see services/historico/orchestration.py
for when an import, the daily alert refresh or the weekly digest is due.
Set HISTORICO_FORCE=true to import now regardless of the schedule.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from .database import SessionLocal
from .hist_scope import use_country
from .services.historico import import_service, notify, orchestration
from .services.historico.alerts_service import refresh_days_and_alerts


def main() -> None:
    force = os.getenv("HISTORICO_FORCE", "false").strip().lower() in {"1", "true", "yes"}
    country = os.getenv("HISTORICO_COUNTRY", "peru").strip().lower() or "peru"
    db = use_country(SessionLocal(), country)
    summary: dict[str, object] = {"country": country}
    try:
        now = orchestration.local_now(db)
        today = now.date()
        if force or orchestration.import_is_due(db, now):
            orchestration.clear_refresh_request(db)
            run = import_service.create_run(db, "azure_job")
            work_dir = Path(tempfile.mkdtemp(prefix=f"historico-{country}-"))
            try:
                run = import_service.download_and_import(db, run, work_dir, today=today)
            finally:
                shutil.rmtree(work_dir, ignore_errors=True)
            orchestration.record_job_result(db, run)
            summary.update(import_run=run.id, status=run.status, error=run.error or None)
            if run.status == "completed":
                orchestration.mark_daily_refresh(db, today)
        elif orchestration.daily_refresh_due(db, today):
            summary["alerts"] = refresh_days_and_alerts(db, today)
            orchestration.mark_daily_refresh(db, today)
        else:
            summary["skipped"] = True
        if orchestration.manual_notice_due(db):
            summary["manual_notice_sent"] = notify.send_manual_upload_notice(db, "la descarga automática y el script de la PC no completaron la carga")
            orchestration.mark_manual_notice_sent(db)
        if orchestration.digest_due(db, now):
            summary["digest_sent"] = notify.send_digest(db, today)
            orchestration.mark_digest_sent(db, today)
    finally:
        db.close()
    print(json.dumps(summary, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
