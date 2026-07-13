from __future__ import annotations

import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Alert, AlertRule, Opportunity, OpportunitySnapshot
import requests

PRIORITY_ORDER = {"A": 3, "B": 2, "C": 1}


def _priority_at_least(value: str, minimum: str) -> bool:
    return PRIORITY_ORDER.get(str(value or "C").upper(), 0) >= PRIORITY_ORDER.get(str(minimum or "A").upper(), 0)


def _deadline_for(opportunity: Opportunity):
    return opportunity.quote_deadline or opportunity.proposal_deadline or opportunity.consultation_deadline


def _build_message(opportunity: Opportunity, alert_type: str) -> str:
    return (
        f"{alert_type}: {opportunity.nomenclature} | {opportunity.entity} | "
        f"prioridad {opportunity.priority} | score {opportunity.score} | {opportunity.detail_url}"
    )


def evaluate_new_opportunity_alerts(db: Session, run_id: int) -> list[Alert]:
    created: list[Alert] = []
    rules = list(db.scalars(select(AlertRule).where(AlertRule.is_active.is_(True))).all())
    if not rules:
        return created

    snapshots = list(
        db.scalars(
            select(OpportunitySnapshot)
            .where(
                OpportunitySnapshot.run_id == run_id,
                OpportunitySnapshot.change_type == "created",
            )
            .order_by(OpportunitySnapshot.created_at.desc())
        ).all()
    )
    if not snapshots:
        return created

    seen_opportunity_ids = set()
    for snapshot in snapshots:
        if snapshot.opportunity_id in seen_opportunity_ids:
            continue
        seen_opportunity_ids.add(snapshot.opportunity_id)
        opp = db.get(Opportunity, snapshot.opportunity_id)
        if not opp:
            continue
        for rule in rules:
            if not _priority_at_least(opp.priority, rule.min_priority):
                continue
            existing = db.scalar(
                select(Alert).where(
                    Alert.opportunity_id == opp.id,
                    Alert.rule_id == rule.id,
                    Alert.alert_type == "new_process",
                )
            )
            if existing:
                continue
            alert = Alert(
                opportunity_id=opp.id,
                rule_id=rule.id,
                alert_type="new_process",
                status="pending",
                message=_build_message(opp, "new_process"),
            )
            db.add(alert)
            created.append(alert)
    db.commit()
    for alert in created:
        db.refresh(alert)
    return created


def evaluate_alerts(db: Session) -> list[Alert]:
    created: list[Alert] = []
    rules = list(db.scalars(select(AlertRule).where(AlertRule.is_active.is_(True))).all())
    if not rules:
        return created

    opportunities = list(db.scalars(select(Opportunity).order_by(Opportunity.updated_at.desc()).limit(500)).all())
    now = datetime.utcnow()

    for rule in rules:
        for opp in opportunities:
            if not _priority_at_least(opp.priority, rule.min_priority):
                continue
            deadline = _deadline_for(opp)
            alert_type = "priority_match"
            if deadline and now <= deadline <= now + timedelta(hours=rule.hours_before_deadline):
                alert_type = "deadline"
            elif opp.priority != "A":
                continue

            existing = db.scalar(
                select(Alert).where(
                    Alert.opportunity_id == opp.id,
                    Alert.rule_id == rule.id,
                    Alert.alert_type == alert_type,
                )
            )
            if existing:
                continue
            alert = Alert(
                opportunity_id=opp.id,
                rule_id=rule.id,
                alert_type=alert_type,
                status="pending",
                message=_build_message(opp, alert_type),
            )
            db.add(alert)
            created.append(alert)
    db.commit()
    for alert in created:
        db.refresh(alert)
    return created


def _send_email(destination: str, message: str) -> None:
    if not settings.smtp_host or not settings.smtp_from:
        raise RuntimeError("SMTP no configurado. Definir SMTP_HOST y SMTP_FROM.")
    email = EmailMessage()
    email["Subject"] = "SEACE Radar - alerta de oportunidad"
    email["From"] = settings.smtp_from
    email["To"] = destination
    email.set_content(message)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(email)


def _send_whatsapp(destination: str, message: str) -> None:
    if not settings.whatsapp_api_url or not settings.whatsapp_token:
        raise RuntimeError("WhatsApp no configurado. Definir WHATSAPP_API_URL y WHATSAPP_TOKEN.")
    payload = {
        "to": destination,
        "from": settings.whatsapp_from,
        "type": "text",
        "text": {"body": message},
    }
    response = requests.post(
        settings.whatsapp_api_url,
        json=payload,
        headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
        timeout=30,
    )
    response.raise_for_status()


def _send_in_app_message(destination: str, message: str) -> None:
    return None


def send_pending_alerts(db: Session, limit: int = 50) -> list[Alert]:
    alerts = list(
        db.scalars(
            select(Alert)
            .where(Alert.status == "pending")
            .order_by(Alert.created_at.asc())
            .limit(limit)
        ).all()
    )
    for alert in alerts:
        rule = db.get(AlertRule, alert.rule_id)
        if not rule or not rule.is_active:
            alert.status = "skipped"
            continue
        try:
            if rule.channel == "email":
                _send_email(rule.destination, alert.message)
            elif rule.channel == "whatsapp":
                _send_whatsapp(rule.destination, alert.message)
            elif rule.channel in {"message", "mensaje", "in_app"}:
                _send_in_app_message(rule.destination, alert.message)
            else:
                raise RuntimeError(f"Canal no soportado: {rule.channel}")
            alert.status = "sent"
            alert.sent_at = datetime.utcnow()
        except Exception as exc:
            alert.status = "error"
            alert.message = f"{alert.message}\n\nDelivery error: {type(exc).__name__}: {exc}"
    db.commit()
    for alert in alerts:
        db.refresh(alert)
    return alerts
