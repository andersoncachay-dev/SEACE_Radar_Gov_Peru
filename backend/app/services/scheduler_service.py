from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from ..config import settings
from ..database import SessionLocal
from ..models import RadarKeyword, ScrapeRun, SearchProfile
from ..radar_config import AUTO_PROFILE_PREFIX, DEFAULT_RADAR_KEYWORDS, RADAR_COUNTRY_CONFIG
from .notification_service import send_pending_alerts
from .run_service import execute_scrape_run

scheduler = None


def sync_radar_profiles(db) -> list[SearchProfile]:
    expected_names: set[str] = set()
    existing_auto = {
        profile.name: profile
        for profile in db.scalars(select(SearchProfile).where(SearchProfile.name.startswith(f"{AUTO_PROFILE_PREFIX} ·"))).all()
    }
    custom_by_country = {
        country: list(
            db.scalars(
                select(RadarKeyword)
                .where(RadarKeyword.country == country)
                .order_by(RadarKeyword.created_at.asc(), RadarKeyword.id.asc())
            ).all()
        )
        for country in RADAR_COUNTRY_CONFIG
    }
    current_year = str(datetime.utcnow().year)
    for country, config in RADAR_COUNTRY_CONFIG.items():
        keywords = [*DEFAULT_RADAR_KEYWORDS, *(item.keyword for item in custom_by_country[country])]
        for keyword in keywords:
            name = f"{AUTO_PROFILE_PREFIX} · {config['label']} · {keyword}"
            expected_names.add(name)
            profile = existing_auto.get(name)
            if profile is None:
                profile = SearchProfile(name=name, keyword=keyword, owner_id=None)
                db.add(profile)
                existing_auto[name] = profile
            profile.source = config["source"]
            profile.year = current_year
            profile.version = config["version"]
            profile.max_results = config["max_results"]
            profile.is_active = True
    for name, profile in existing_auto.items():
        if name not in expected_names:
            profile.is_active = False
    db.commit()
    return list(existing_auto.values())


def enqueue_active_profiles(country: str | None = None) -> dict[str, int]:
    db = SessionLocal()
    summary = {"profiles": 0, "completed": 0, "failed": 0, "rows_found": 0}
    try:
        sync_radar_profiles(db)
        query = select(SearchProfile).where(SearchProfile.is_active.is_(True))
        if country:
            config = RADAR_COUNTRY_CONFIG.get(country)
            if config is None:
                raise ValueError(f"País de ingesta no soportado: {country}")
            query = query.where(SearchProfile.source == config["source"])
        profiles = list(db.scalars(query).all())
        summary["profiles"] = len(profiles)
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
            db.expire(run)
            db.refresh(run)
            if run.status == "completed":
                summary["completed"] += 1
                summary["rows_found"] += run.rows_found
            else:
                summary["failed"] += 1
        return summary
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
