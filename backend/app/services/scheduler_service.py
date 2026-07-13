from __future__ import annotations

from sqlalchemy import select

from ..config import settings
from ..database import SessionLocal
from ..models import ScrapeRun, SearchProfile
from .notification_service import send_pending_alerts
from .run_service import execute_scrape_run

scheduler = None


def enqueue_active_profiles() -> None:
    db = SessionLocal()
    try:
        profiles = list(db.scalars(select(SearchProfile).where(SearchProfile.is_active.is_(True))).all())
        for profile in profiles:
            run = ScrapeRun(search_profile_id=profile.id, source=profile.source, status="queued")
            db.add(run)
            db.commit()
            db.refresh(run)
            execute_scrape_run(
                run.id,
                {
                    "search_profile_id": profile.id,
                    "source": profile.source,
                    "keyword": profile.keyword,
                    "year": profile.year,
                    "version": profile.version,
                    "max_results": profile.max_results,
                    "max_details": min(profile.max_results, 15),
                    "enrich_details": False,
                },
            )
    finally:
        db.close()


def send_pending_alerts_job() -> None:
    db = SessionLocal()
    try:
        send_pending_alerts(db)
    finally:
        db.close()


def start_scheduler() -> None:
    global scheduler
    if not settings.enable_scheduler or scheduler is not None:
        return
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(timezone="America/Lima")
    scheduler.add_job(
        enqueue_active_profiles,
        trigger="interval",
        minutes=settings.scheduler_interval_minutes,
        id="active-search-profiles",
        replace_existing=True,
    )
    scheduler.add_job(
        send_pending_alerts_job,
        trigger="interval",
        minutes=settings.alert_sender_interval_minutes,
        id="pending-alert-sender",
        replace_existing=True,
    )
    scheduler.start()


def stop_scheduler() -> None:
    global scheduler
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        scheduler = None
