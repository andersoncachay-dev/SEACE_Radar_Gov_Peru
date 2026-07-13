from __future__ import annotations

import pandas as pd
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..config import settings
from ..models import Opportunity, OpportunitySnapshot, ScrapeRun, User
from ..schemas import OpportunityImportIn, OpportunityImportResult, OpportunityOut, OpportunitySnapshotOut
from ..services.ingestion_service import upsert_opportunities
from ..services.notification_service import evaluate_alerts, evaluate_new_opportunity_alerts, send_pending_alerts
from ..services.seace_excel_service import read_seace_export

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.get("/stats")
def opportunity_stats(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    opportunities = list(db.scalars(select(Opportunity)).all())
    by_source: dict[str, int] = {}
    by_priority: dict[str, int] = {"A": 0, "B": 0, "C": 0}
    total_amount = 0.0
    vigentes = 0
    cerrados = 0
    for item in opportunities:
        by_source[item.source] = by_source.get(item.source, 0) + 1
        by_priority[item.priority] = by_priority.get(item.priority, 0) + 1
        total_amount += float(item.amount or 0)
        status = str(item.status or "").lower()
        if "vigente" in status:
            vigentes += 1
        if "cerrado" in status:
            cerrados += 1
    return {
        "total": len(opportunities),
        "by_source": by_source,
        "by_priority": by_priority,
        "vigentes": vigentes,
        "cerrados": cerrados,
        "total_amount": total_amount,
    }


@router.get("", response_model=list[OpportunityOut])
def list_opportunities(
    source: str | None = None,
    priority: str | None = None,
    status: str | None = None,
    run_id: int | None = None,
    run_ids: str | None = None,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = select(Opportunity)
    run_filter_ids: list[int] = []
    if run_id is not None:
        run_filter_ids.append(run_id)
    if run_ids:
        for raw_id in run_ids.split(","):
            try:
                run_filter_ids.append(int(raw_id.strip()))
            except ValueError:
                continue
    if run_filter_ids:
        query = (
            query.join(OpportunitySnapshot, OpportunitySnapshot.opportunity_id == Opportunity.id)
            .where(OpportunitySnapshot.run_id.in_(sorted(set(run_filter_ids))))
            .distinct()
        )
    if source:
        query = query.where(Opportunity.source == source)
    if priority:
        query = query.where(Opportunity.priority == priority)
    if status:
        query = query.where(Opportunity.status == status)
    query = query.order_by(Opportunity.updated_at.desc()).limit(500)
    return list(db.scalars(query).all())


@router.post("/import", response_model=OpportunityImportResult)
def import_opportunities(
    payload: OpportunityImportIn,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    df = pd.DataFrame(payload.rows or [])
    count = upsert_opportunities(db, df, payload.source)
    return {"imported": count}


@router.post("/import-seace-excel", response_model=OpportunityImportResult)
async def import_seace_excel(
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    suffix = Path(file.filename or "").suffix or ".xls"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        df = read_seace_export(tmp_path)
        run = ScrapeRun(
            source="seace_public_excel",
            status="running",
            started_at=datetime.utcnow(),
            diagnostics=f"Archivo importado: {file.filename}",
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        count = upsert_opportunities(db, df, "seace_public_excel", run_id=run.id)
        run.rows_found = count
        run.status = "completed"
        run.finished_at = datetime.utcnow()
        db.commit()
        evaluate_new_opportunity_alerts(db, run.id)
        evaluate_alerts(db)
        if settings.auto_send_alerts:
            send_pending_alerts(db)
        return {"imported": count}
    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("/{opportunity_id}/snapshots", response_model=list[OpportunitySnapshotOut])
def list_snapshots(
    opportunity_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (
        select(OpportunitySnapshot)
        .where(OpportunitySnapshot.opportunity_id == opportunity_id)
        .order_by(OpportunitySnapshot.created_at.desc())
        .limit(100)
    )
    return list(db.scalars(query).all())
