from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from ..config import settings
from ..database import SessionLocal
from ..models import AppSetting, RadarKeyword, ScrapeRun, SearchProfile
from ..radar_config import AUTO_PROFILE_PREFIX, DEFAULT_RADAR_KEYWORDS, RADAR_COUNTRY_CONFIG
from .notification_service import send_pending_alerts
from .run_service import execute_scrape_run

scheduler = None
LIMA_TIMEZONE = ZoneInfo("America/Lima")
SUPPORTED_COUNTRIES = ("peru", "chile")
DEFAULT_INTERVAL_SECONDS = 15 * 60
DEFAULT_INCREMENTAL_LOOKBACK_DAYS = 2
CHILE_INCREMENTAL_FUTURE_DAYS = 38


def external_scheduler_next_run(country: str, now: datetime | None = None) -> datetime | None:
    if not settings.external_scheduler_enabled:
        return None
    normalized_country = str(country or "").strip().lower()
    if normalized_country not in SUPPORTED_COUNTRIES:
        raise ValueError(f"PaÃ­s de scheduler no soportado: {country}")
    interval_seconds = max(60, settings.external_scheduler_interval_minutes * 60)
    offset_seconds = 0 if normalized_country == "peru" else min(5 * 60, interval_seconds // 3)
    current = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)
    current_epoch = int(current.timestamp())
    next_epoch = ((current_epoch - offset_seconds) // interval_seconds + 1) * interval_seconds + offset_seconds
    return datetime.fromtimestamp(next_epoch, timezone.utc)


def scheduler_initial_delay(country: str, interval_seconds: int) -> int:
    """Keep country jobs out of phase while preserving each configured interval."""
    if country == "peru":
        return interval_seconds
    chile_offset = min(5 * 60, max(30, interval_seconds // 3))
    return interval_seconds + chile_offset


def _interval_key(country: str) -> str:
    return f"scheduler.{country}.interval_seconds"


def _next_update_key(country: str) -> str:
    return f"scheduler.{country}.next_update_at"


def _read_datetime_setting(db, key: str) -> datetime | None:
    item = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if item is None:
        return None
    try:
        parsed = datetime.fromisoformat(item.value)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _write_setting(db, key: str, value: str, user_id: int | None = None) -> None:
    item = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if item is None:
        db.add(AppSetting(key=key, value=value, updated_by_id=user_id))
    else:
        item.value = value
        item.updated_by_id = user_id


def get_external_next_update(db, country: str, now: datetime | None = None) -> datetime:
    """Return the persisted due time used by the minute-level Azure job."""
    normalized_country = str(country or "").strip().lower()
    if normalized_country not in SUPPORTED_COUNTRIES:
        raise ValueError(f"País de scheduler no soportado: {country}")
    next_update = _read_datetime_setting(db, _next_update_key(normalized_country))
    if next_update is not None:
        return next_update
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    next_update = current + timedelta(seconds=get_scheduler_interval(db, normalized_country))
    _write_setting(db, _next_update_key(normalized_country), next_update.isoformat())
    db.commit()
    return next_update


def claim_external_scheduler_run(country: str, now: datetime | None = None) -> tuple[bool, datetime]:
    """Atomically advance one country's due time when its Azure job may run."""
    normalized_country = str(country or "").strip().lower()
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    db = SessionLocal()
    try:
        due_at = get_external_next_update(db, normalized_country, current)
        if current < due_at:
            return False, due_at
        next_update = current + timedelta(seconds=get_scheduler_interval(db, normalized_country))
        _write_setting(db, _next_update_key(normalized_country), next_update.isoformat())
        db.commit()
        return True, next_update
    finally:
        db.close()


def get_scheduler_interval(db, country: str) -> int:
    normalized_country = str(country or "").strip().lower()
    if normalized_country not in SUPPORTED_COUNTRIES:
        raise ValueError(f"País de scheduler no soportado: {country}")
    item = db.scalar(select(AppSetting).where(AppSetting.key == _interval_key(normalized_country)))
    if item is None:
        return DEFAULT_INTERVAL_SECONDS
    try:
        return max(60, int(item.value))
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL_SECONDS


def scheduler_interval_config(country: str) -> dict[str, object]:
    normalized_country = str(country or "").strip().lower()
    db = SessionLocal()
    try:
        interval_seconds = get_scheduler_interval(db, normalized_country)
    finally:
        db.close()
    job = scheduler.get_job(f"active-search-profiles-{normalized_country}") if scheduler is not None else None
    days, remainder = divmod(interval_seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes = remainder // 60
    external_next_run = None
    if settings.external_scheduler_enabled:
        db = SessionLocal()
        try:
            external_next_run = get_external_next_update(db, normalized_country)
        finally:
            db.close()
    return {
        "country": normalized_country,
        "days": days,
        "hours": hours,
        "minutes": minutes,
        "interval_seconds": interval_seconds,
        "next_update_at": job.next_run_time.isoformat() if job and job.next_run_time else external_next_run,
        "enabled": bool((settings.enable_scheduler and job is not None) or settings.external_scheduler_enabled),
    }


def save_scheduler_interval(country: str, interval_seconds: int, user_id: int | None) -> dict[str, object]:
    normalized_country = str(country or "").strip().lower()
    if normalized_country not in SUPPORTED_COUNTRIES:
        raise ValueError(f"País de scheduler no soportado: {country}")
    interval_seconds = max(60, int(interval_seconds))
    db = SessionLocal()
    try:
        _write_setting(db, _interval_key(normalized_country), str(interval_seconds), user_id)
        _write_setting(
            db,
            _next_update_key(normalized_country),
            (datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)).isoformat(),
            user_id,
        )
        db.commit()
    finally:
        db.close()
    if scheduler is not None:
        scheduler.add_job(
            enqueue_active_profiles,
            trigger="interval",
            seconds=interval_seconds,
            next_run_time=datetime.now(LIMA_TIMEZONE) + timedelta(seconds=scheduler_initial_delay(normalized_country, interval_seconds)),
            kwargs={"country": normalized_country},
            id=f"active-search-profiles-{normalized_country}",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
    return scheduler_interval_config(normalized_country)


def current_ingestion_period(now: datetime | None = None) -> dict[str, object]:
    """Return the single calendar month processed by automatic ingestion."""
    current = now.astimezone(LIMA_TIMEZONE) if now else datetime.now(LIMA_TIMEZONE)
    year = str(current.year)
    month = str(current.month)
    return {"year": year, "month": month, "years": [year], "months": [month]}


def current_ingestion_window(db, country: str, now: datetime | None = None) -> dict[str, object]:
    current = now.astimezone(LIMA_TIMEZONE) if now else datetime.now(LIMA_TIMEZONE)
    normalized_country = str(country or "").strip().lower()
    start_date = current.date() - timedelta(days=DEFAULT_INCREMENTAL_LOOKBACK_DAYS)
    # The first ChileCompra result contains the proposal closing date. Searching
    # that field into the future discovers tenders published today whose closing
    # date is several weeks away. Peru keeps its publication-date window.
    is_chile = normalized_country == "chile"
    end_date = current.date() + timedelta(days=CHILE_INCREMENTAL_FUTURE_DAYS) if is_chile else current.date()
    month_cursor = start_date.replace(day=1)
    covered: list[tuple[int, int]] = []
    while month_cursor <= end_date:
        covered.append((month_cursor.year, month_cursor.month))
        month_cursor = (month_cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return {
        "year": str(end_date.year),
        "month": str(end_date.month),
        "years": sorted({str(year) for year, _ in covered}),
        "months": sorted({str(month) for _, month in covered}, key=int),
        "publication_date_from": start_date.isoformat(),
        "publication_date_to": end_date.isoformat(),
        "date_filter_type": "closing" if is_chile else "publication",
        "active_only": True,
        "automatic_incremental": True,
        "skip_detail_enrichment": is_chile,
    }


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
        ingestion_period = current_ingestion_window(db, country) if country else current_ingestion_period()
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
                    **ingestion_period,
                    "version": profile.version,
                    "max_results": profile.max_results,
                    "max_details": min(profile.max_results, 30),
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


def scheduler_status(country: str) -> dict[str, object]:
    normalized_country = str(country or "").strip().lower()
    if normalized_country not in SUPPORTED_COUNTRIES:
        raise ValueError(f"País de scheduler no soportado: {country}")
    job = scheduler.get_job(f"active-search-profiles-{normalized_country}") if scheduler is not None else None
    next_run = job.next_run_time if job is not None else None
    db = SessionLocal()
    try:
        interval_seconds = get_scheduler_interval(db, normalized_country)
        if settings.external_scheduler_enabled and next_run is None:
            next_run = get_external_next_update(db, normalized_country)
        source = RADAR_COUNTRY_CONFIG[normalized_country]["source"]
        active_run_id = db.scalar(
            select(ScrapeRun.id)
            .where(ScrapeRun.source == source, ScrapeRun.status.in_(("queued", "running")))
            .limit(1)
        )
    finally:
        db.close()
    return {
        "enabled": bool((settings.enable_scheduler and job is not None) or settings.external_scheduler_enabled),
        "country": normalized_country,
        "is_running": active_run_id is not None,
        "next_update_at": next_run.isoformat() if next_run is not None else None,
        "interval_minutes": interval_seconds // 60,
        "interval_seconds": interval_seconds,
    }


def start_scheduler() -> None:
    global scheduler
    if not settings.enable_scheduler or scheduler is not None:
        return
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(timezone="America/Lima")
    db = SessionLocal()
    try:
        country_intervals = {country: get_scheduler_interval(db, country) for country in SUPPORTED_COUNTRIES}
    finally:
        db.close()
    for country, interval_seconds in country_intervals.items():
        scheduler.add_job(
            enqueue_active_profiles,
            trigger="interval",
            seconds=interval_seconds,
            next_run_time=datetime.now(LIMA_TIMEZONE) + timedelta(seconds=scheduler_initial_delay(country, interval_seconds)),
            kwargs={"country": country},
            id=f"active-search-profiles-{country}",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
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
