from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user, require_admin
from ..models import Alert, AlertRule, Opportunity, OpportunitySnapshot, User
from ..radar_config import country_for_source
from ..schemas import AlertOut, AlertRuleCreate, AlertRuleOut, AlertRuleUpdate
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


@router.patch("/rules/{rule_id}", response_model=AlertRuleOut)
def update_rule(
    rule_id: int,
    payload: AlertRuleUpdate,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rule = db.get(AlertRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Regla de alerta no encontrada")

    changes = payload.model_dump(exclude_unset=True)
    validated = AlertRuleCreate(
        name=changes.get("name", rule.name),
        channel=changes.get("channel", rule.channel),
        destination=changes.get("destination", rule.destination),
        keywords=changes.get("keywords", rule.keywords),
        min_priority=changes.get("min_priority", rule.min_priority),
        country=changes.get("country", rule.country),
        is_active=changes.get("is_active", rule.is_active),
    )
    for field, value in validated.model_dump().items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = db.get(AlertRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Regla de alerta no encontrada")
    db.execute(delete(Alert).where(Alert.rule_id == rule_id))
    db.delete(rule)
    db.commit()
    return None


@router.get("", response_model=list[AlertOut])
def list_alerts(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    alerts = list(db.scalars(select(Alert).order_by(Alert.created_at.desc()).limit(200)).all())
    opportunity_ids = {alert.opportunity_id for alert in alerts}
    rule_ids = {alert.rule_id for alert in alerts}
    opportunities = {
        row[0]: (row[1], row[2], row[3])
        for row in db.execute(
            select(Opportunity.id, Opportunity.source, Opportunity.entity, Opportunity.description).where(
                Opportunity.id.in_(opportunity_ids)
            )
        ).all()
    } if opportunity_ids else {}
    rule_info = {
        row[0]: (row[1], row[2], row[3], row[4])
        for row in db.execute(
            select(AlertRule.id, AlertRule.channel, AlertRule.is_active, AlertRule.destination, AlertRule.keywords).where(
                AlertRule.id.in_(rule_ids)
            )
        ).all()
    } if rule_ids else {}
    # The run that first discovered each opportunity - the earliest "created"
    # snapshot - is the run behind this alert.
    discovery_run_by_opportunity: dict[int, int] = {}
    if opportunity_ids:
        snapshot_rows = db.execute(
            select(OpportunitySnapshot.opportunity_id, OpportunitySnapshot.run_id)
            .where(
                OpportunitySnapshot.opportunity_id.in_(opportunity_ids),
                OpportunitySnapshot.change_type == "created",
            )
            .order_by(OpportunitySnapshot.created_at.asc())
        ).all()
        for opportunity_id, run_id in snapshot_rows:
            discovery_run_by_opportunity.setdefault(opportunity_id, run_id)
    results = []
    for alert in alerts:
        opportunity = opportunities.get(alert.opportunity_id)
        channel, rule_is_active, destination, keywords = rule_info.get(alert.rule_id, ("email", True, "", ""))
        data = AlertOut.model_validate(alert).model_dump()
        data["country"] = country_for_source(opportunity[0] if opportunity else "")
        data["entity"] = (opportunity[1] if opportunity else "") or ""
        data["description"] = (opportunity[2] if opportunity else "") or ""
        data["channel"] = channel
        data["rule_is_active"] = rule_is_active
        data["destination"] = destination or ""
        data["keywords"] = keywords or ""
        data["run_id"] = discovery_run_by_opportunity.get(alert.opportunity_id)
        results.append(data)
    return results


@router.post("/evaluate", response_model=list[AlertOut])
def run_alert_evaluation(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return evaluate_alerts(db)


@router.post("/send-pending", response_model=list[AlertOut])
def send_alerts(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return send_pending_alerts(db)
