from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user, require_source_access, source_access_condition
from ..models import ScrapeRun, SearchProfile, User
from ..schemas import RunStart, ScrapeRunOut
from ..services.run_service import execute_scrape_run, request_run_cancel
from ..services.scheduler_service import enqueue_active_profiles, force_scheduler_run, scheduler_status

router = APIRouter(prefix="/runs", tags=["runs"])


def _disable_progress_cache(response: Response) -> None:
    """Progress endpoints must always reflect the latest committed run state."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"


@router.get("/scheduler/status")
def get_scheduler_status(
    country: Literal["peru", "chile"],
    current_user: User = Depends(get_current_user),
):
    return scheduler_status(country)


@router.post("/scheduler/trigger")
def trigger_scheduler_run(
    country: Literal["peru", "chile"],
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    if scheduler_status(country)["is_running"]:
        raise HTTPException(status_code=409, detail="Ya hay una actualización en curso para este país.")
    force_scheduler_run(country)
    background_tasks.add_task(enqueue_active_profiles, country=country)
    return scheduler_status(country)


@router.get("", response_model=list[ScrapeRunOut])
def list_runs(response: Response, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _disable_progress_cache(response)
    query = select(ScrapeRun)
    access_condition = source_access_condition(ScrapeRun.source, current_user)
    if access_condition is not None:
        query = query.where(access_condition)
    return list(db.scalars(query.order_by(ScrapeRun.created_at.desc()).limit(100)).all())


@router.get("/{run_id}", response_model=ScrapeRunOut)
def get_run(run_id: int, response: Response, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _disable_progress_cache(response)
    run = db.get(ScrapeRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    require_source_access(current_user, run.source)
    return run


@router.post("/{run_id}/cancel", response_model=ScrapeRunOut)
def cancel_run(run_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.get(ScrapeRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    require_source_access(current_user, run.source)
    if run.status in {"completed", "failed", "cancelled"}:
        return run
    run.cancel_requested = True
    run.status = "cancelled"
    run.progress_message = "Búsqueda detenida"
    run.error_message = ""
    run.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(run)
    request_run_cancel(run.id)
    return run


@router.post("/start", response_model=ScrapeRunOut, status_code=status.HTTP_202_ACCEPTED)
def start_run(
    payload: RunStart,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.search_profile_id:
        profile = db.get(SearchProfile, payload.search_profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Search profile not found")
        source = profile.source
    else:
        source = payload.source
    require_source_access(current_user, source)
    run = ScrapeRun(search_profile_id=payload.search_profile_id, source=source, status="queued")
    db.add(run)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(execute_scrape_run, run.id, payload.dict())
    return run
