from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import Alert, AlertRule, User
from ..schemas import AlertOut, AlertRuleCreate, AlertRuleOut
from ..services.notification_service import evaluate_alerts, send_pending_alerts

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/rules", response_model=list[AlertRuleOut])
def list_rules(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(AlertRule).order_by(AlertRule.created_at.desc())).all())


@router.post("/rules", response_model=AlertRuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(payload: AlertRuleCreate, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = AlertRule(**payload.dict())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("", response_model=list[AlertOut])
def list_alerts(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(Alert).order_by(Alert.created_at.desc()).limit(200)).all())


@router.post("/evaluate", response_model=list[AlertOut])
def run_alert_evaluation(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return evaluate_alerts(db)


@router.post("/send-pending", response_model=list[AlertOut])
def send_alerts(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return send_pending_alerts(db)
