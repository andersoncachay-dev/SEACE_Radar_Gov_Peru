from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import ScrapeRun, SearchProfile, User
from ..schemas import RunStart, ScrapeRunOut
from ..services.run_service import execute_scrape_run

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=list[ScrapeRunOut])
def list_runs(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(ScrapeRun).order_by(ScrapeRun.created_at.desc()).limit(100)).all())


@router.get("/{run_id}", response_model=ScrapeRunOut)
def get_run(run_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.get(ScrapeRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("/start", response_model=ScrapeRunOut, status_code=status.HTTP_202_ACCEPTED)
def start_run(
    payload: RunStart,
    background_tasks: BackgroundTasks,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.search_profile_id:
        profile = db.get(SearchProfile, payload.search_profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Search profile not found")
        source = profile.source
    else:
        source = payload.source
    run = ScrapeRun(search_profile_id=payload.search_profile_id, source=source, status="queued")
    db.add(run)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(execute_scrape_run, run.id, payload.dict())
    return run
