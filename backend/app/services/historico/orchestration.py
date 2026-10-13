"""When Histórico Perú refreshes, and what happens when a refresh fails.

The govradar-historico-peru Container Apps Job fires hourly and is a no-op
almost every time (claim pattern, like scheduler_service). Real work:

* monthly import: from ``refresh_day`` (default 9, OECE publishes in the
  first five days) until an import completes that month, or right away
  when an admin presses "Actualizar ahora" (``refresh_requested``);
* daily: recompute days-to-go and re-evaluate alerts;
* weekly (Monday 8:00 Lima): email digest.

Fallback chain: Azure job -> PC script (polls ``status()['needs_fallback']``)
-> email to admins asking for a manual upload.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import AppSetting, HistImportRun

KEY_REFRESH_DAY = "historico.peru.refresh_day"
KEY_REFRESH_REQUESTED = "historico.peru.refresh_requested"
KEY_DAILY_DONE = "historico.peru.daily_refreshed_on"
KEY_DIGEST_SENT = "historico.peru.digest_sent_on"
KEY_JOB_FAILED_AT = "historico.peru.job_failed_at"
KEY_MANUAL_NOTICE_AT = "historico.peru.manual_notice_sent_at"
DEFAULT_REFRESH_DAY = 9
STALE_RUNNING_HOURS = 3
PC_GRACE_HOURS = 24
MANUAL_NOTICE_EVERY_DAYS = 3


def lima_now() -> datetime:
    return datetime.utcnow() - timedelta(hours=5)


def get_setting(db: Session, key: str, default: str = "") -> str:
    item = db.scalar(select(AppSetting).where(AppSetting.key == key))
    return item.value if item else default


def set_setting(db: Session, key: str, value: str, user_id: int | None = None) -> None:
    item = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if item is None:
        db.add(AppSetting(key=key, value=value, updated_by_id=user_id))
    else:
        item.value = value
        item.updated_by_id = user_id
    db.commit()


def refresh_day(db: Session) -> int:
    try:
        return min(28, max(1, int(get_setting(db, KEY_REFRESH_DAY, str(DEFAULT_REFRESH_DAY)))))
    except ValueError:
        return DEFAULT_REFRESH_DAY


def _completed_this_month(db: Session, today: date) -> HistImportRun | None:
    month_start = datetime(today.year, today.month, 1) + timedelta(hours=5)  # Lima midnight in UTC
    return db.scalar(
        select(HistImportRun)
        .where(HistImportRun.status == "completed", HistImportRun.finished_at >= month_start, HistImportRun.origin != "manual_upload")
        .order_by(HistImportRun.finished_at.desc())
        .limit(1)
    )


def running_import(db: Session) -> HistImportRun | None:
    cutoff = datetime.utcnow() - timedelta(hours=STALE_RUNNING_HOURS)
    return db.scalar(
        select(HistImportRun).where(HistImportRun.status.in_(("receiving", "queued", "running")), HistImportRun.created_at >= cutoff).limit(1)
    )


def import_is_due(db: Session, now: datetime | None = None) -> bool:
    now = now or lima_now()
    if running_import(db):
        return False
    if get_setting(db, KEY_REFRESH_REQUESTED) == "true":
        return True
    return now.day >= refresh_day(db) and _completed_this_month(db, now.date()) is None


def request_refresh(db: Session, user_id: int | None) -> None:
    set_setting(db, KEY_REFRESH_REQUESTED, "true", user_id)


def clear_refresh_request(db: Session) -> None:
    if get_setting(db, KEY_REFRESH_REQUESTED) == "true":
        set_setting(db, KEY_REFRESH_REQUESTED, "false")


def record_job_result(db: Session, run: HistImportRun) -> None:
    if run.status == "completed":
        set_setting(db, KEY_JOB_FAILED_AT, "")
    elif not get_setting(db, KEY_JOB_FAILED_AT):
        set_setting(db, KEY_JOB_FAILED_AT, datetime.utcnow().isoformat())


def needs_fallback(db: Session) -> bool:
    """True while the Azure job failed this cycle and nothing has succeeded since."""
    failed_at = get_setting(db, KEY_JOB_FAILED_AT)
    if not failed_at:
        return False
    latest = db.scalar(select(HistImportRun).where(HistImportRun.status == "completed").order_by(HistImportRun.finished_at.desc()).limit(1))
    return not (latest and latest.finished_at and latest.finished_at.isoformat() > failed_at)


def manual_notice_due(db: Session, *, pc_failed: bool = False) -> bool:
    """Ask admins for a manual upload when the PC script also failed, or
    never showed up within PC_GRACE_HOURS of the job failure."""
    if not needs_fallback(db):
        return False
    last_notice = get_setting(db, KEY_MANUAL_NOTICE_AT)
    if last_notice and datetime.fromisoformat(last_notice) > datetime.utcnow() - timedelta(days=MANUAL_NOTICE_EVERY_DAYS):
        return False
    if pc_failed:
        return True
    failed_at = datetime.fromisoformat(get_setting(db, KEY_JOB_FAILED_AT))
    return datetime.utcnow() - failed_at >= timedelta(hours=PC_GRACE_HOURS)


def mark_manual_notice_sent(db: Session) -> None:
    set_setting(db, KEY_MANUAL_NOTICE_AT, datetime.utcnow().isoformat())


def daily_refresh_due(db: Session, today: date) -> bool:
    return get_setting(db, KEY_DAILY_DONE) != today.isoformat()


def mark_daily_refresh(db: Session, today: date) -> None:
    set_setting(db, KEY_DAILY_DONE, today.isoformat())


def digest_due(db: Session, now: datetime | None = None) -> bool:
    now = now or lima_now()
    return now.weekday() == 0 and now.hour >= 8 and get_setting(db, KEY_DIGEST_SENT) != now.date().isoformat()


def mark_digest_sent(db: Session, today: date) -> None:
    set_setting(db, KEY_DIGEST_SENT, today.isoformat())


def status(db: Session) -> dict:
    latest = db.scalar(select(HistImportRun).order_by(HistImportRun.created_at.desc()).limit(1))
    completed = db.scalar(select(HistImportRun).where(HistImportRun.status == "completed").order_by(HistImportRun.finished_at.desc()).limit(1))
    now = lima_now()
    return {
        "latest_run_id": latest.id if latest else None,
        "latest_status": latest.status if latest else None,
        "latest_completed_at": completed.finished_at.isoformat() if completed and completed.finished_at else None,
        "data_cut_date": completed.data_cut_date.isoformat() if completed and completed.data_cut_date else None,
        "refresh_day": refresh_day(db),
        "refresh_requested": get_setting(db, KEY_REFRESH_REQUESTED) == "true",
        "import_due": import_is_due(db, now),
        "needs_fallback": needs_fallback(db),
        "completed_this_month": _completed_this_month(db, now.date()) is not None,
    }
