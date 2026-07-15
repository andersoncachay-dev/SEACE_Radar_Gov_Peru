from __future__ import annotations

import smtplib
import re
from datetime import datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Alert, AlertRule, Opportunity, OpportunitySnapshot
import requests
from src.keyword_matching import contains_complete_phrase, normalize_search_text

PRIORITY_ORDER = {"A": 3, "B": 2, "C": 1}


def _priority_at_least(value: str, minimum: str) -> bool:
    return PRIORITY_ORDER.get(str(value or "C").upper(), 0) >= PRIORITY_ORDER.get(str(minimum or "A").upper(), 0)


def _normalize_search_text(value: str) -> str:
    return normalize_search_text(value)


def _matches_rule_keywords(description: str, configured_keywords: str) -> bool:
    keywords = [
        _normalize_search_text(item)
        for item in re.split(r"[,;\n]+", configured_keywords or "")
        if _normalize_search_text(item)
    ]
    if not keywords:
        return True
    return any(contains_complete_phrase(description, keyword) for keyword in keywords)


def _deadline_for(opportunity: Opportunity):
    return opportunity.quote_deadline or opportunity.proposal_deadline or opportunity.consultation_deadline


def _build_message(opportunity: Opportunity, alert_type: str) -> str:
    alert_labels = {
        "new_process": "Nueva oportunidad detectada",
        "priority_match": "Oportunidad de alta prioridad",
        "deadline": "Vencimiento comercial próximo",
    }
    deadline = _deadline_for(opportunity)
    deadline_text = deadline.strftime("%d/%m/%Y %H:%M") if deadline else "Sin fecha confirmada"
    return (
        f"GovRadar · {alert_labels.get(alert_type, 'Alerta de oportunidad')}\n\n"
        f"Proceso: {opportunity.nomenclature or 'Sin nomenclatura'}\n"
        f"Entidad: {opportunity.entity or 'Sin entidad'}\n"
        f"Prioridad: {opportunity.priority} · Score: {opportunity.score}\n"
        f"Fecha límite: {deadline_text}\n\n"
        f"Revisar oportunidad: {opportunity.detail_url or 'Disponible en GovRadar'}"
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
            if not _matches_rule_keywords(opp.description, rule.keywords):
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
    # Las reglas se evalúan al detectar procesos nuevos en
    # evaluate_new_opportunity_alerts. No se generan alertas por vencimiento.
    return []


def _send_azure_email(destination: str, message: str, subject: str = "GovRadar · Nueva alerta comercial") -> str:
    if not settings.azure_communication_connection_string or not settings.azure_email_sender:
        raise RuntimeError("Azure Email no configurado. Definir AZURE_COMMUNICATION_CONNECTION_STRING y AZURE_EMAIL_SENDER.")
    from azure.communication.email import EmailClient

    client = EmailClient.from_connection_string(settings.azure_communication_connection_string)
    payload = {
        "senderAddress": settings.azure_email_sender,
        "recipients": {"to": [{"address": destination}]},
        "content": {
            "subject": subject,
            "plainText": message,
            "html": "<br>".join(message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").splitlines()),
        },
    }
    result = client.begin_send(payload).result()
    status = result.get("status") if isinstance(result, dict) else getattr(result, "status", "")
    if str(status).lower() != "succeeded":
        raise RuntimeError(f"Azure Email devolvio estado {status or 'desconocido'}")
    return str(result.get("id", "") if isinstance(result, dict) else getattr(result, "id", ""))


def _send_smtp_email(destination: str, message: str, subject: str = "GovRadar - alerta de oportunidad") -> str:
    if not settings.smtp_host or not settings.smtp_from:
        raise RuntimeError("SMTP no configurado. Definir SMTP_HOST y SMTP_FROM.")
    email = EmailMessage()
    email["Subject"] = subject
    email["From"] = settings.smtp_from
    email["To"] = destination
    email.set_content(message)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(email)
    return str(email.get("Message-ID") or "")


def _send_email(destination: str, message: str, subject: str = "GovRadar · Nueva alerta comercial") -> str:
    if settings.email_provider == "azure":
        return _send_azure_email(destination, message, subject)
    return _send_smtp_email(destination, message, subject)


def _send_azure_whatsapp(destination: str) -> str:
    if not settings.azure_communication_connection_string or not settings.whatsapp_channel_id:
        raise RuntimeError("WhatsApp Azure no configurado. Definir AZURE_COMMUNICATION_CONNECTION_STRING y WHATSAPP_CHANNEL_ID.")
    from azure.communication.messages import NotificationMessagesClient
    from azure.communication.messages.models import MessageTemplate, TemplateNotificationContent

    client = NotificationMessagesClient.from_connection_string(settings.azure_communication_connection_string)
    template = MessageTemplate(
        name=settings.whatsapp_template_name,
        language=settings.whatsapp_template_language,
    )
    content = TemplateNotificationContent(
        channel_registration_id=settings.whatsapp_channel_id,
        to=[destination],
        template=template,
    )
    result = client.send(content)
    receipt = result.receipts[0] if result.receipts else None
    if receipt is None:
        raise RuntimeError("Azure WhatsApp no devolvio confirmacion de envio")
    return str(receipt.message_id or "")


def _send_http_whatsapp(destination: str, message: str) -> str:
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
    try:
        payload = response.json()
        return str(payload.get("message_id") or payload.get("id") or "")
    except Exception:
        return ""


def _send_whatsapp(destination: str, message: str) -> str:
    if settings.whatsapp_provider in {"azure", "azure_acs"}:
        return _send_azure_whatsapp(destination)
    return _send_http_whatsapp(destination, message)


def _send_in_app_message(destination: str, message: str) -> str:
    return "in-app"


def send_pending_alerts(db: Session, limit: int | None = None) -> list[Alert]:
    now = datetime.utcnow()
    effective_limit = limit or settings.alert_batch_size
    alerts = list(
        db.scalars(
            select(Alert)
            .where(
                Alert.status.in_(["pending", "retrying", "error", "waiting_channel"]),
                Alert.attempt_count < settings.alert_max_attempts,
                or_(Alert.next_attempt_at.is_(None), Alert.next_attempt_at <= now),
            )
            .order_by(Alert.created_at.asc())
            .limit(effective_limit)
        ).all()
    )
    for alert in alerts:
        rule = db.get(AlertRule, alert.rule_id)
        if not rule or not rule.is_active:
            alert.status = "skipped"
            continue
        if rule.channel == "whatsapp" and not settings.whatsapp_enabled:
            alert.status = "waiting_channel"
            alert.next_attempt_at = None
            alert.last_error = ""
            continue
        alert.attempt_count += 1
        alert.last_attempt_at = datetime.utcnow()
        alert.last_error = ""
        clean_message = alert.message.split("\n\nDelivery error:", 1)[0]
        alert.message = clean_message
        try:
            if rule.channel == "email":
                provider_message_id = _send_email(rule.destination, clean_message)
            elif rule.channel == "whatsapp":
                provider_message_id = _send_whatsapp(rule.destination, clean_message)
            elif rule.channel in {"message", "mensaje", "in_app"}:
                provider_message_id = _send_in_app_message(rule.destination, clean_message)
            else:
                raise RuntimeError(f"Canal no soportado: {rule.channel}")
            alert.status = "sent"
            alert.sent_at = datetime.utcnow()
            alert.next_attempt_at = None
            alert.provider_message_id = provider_message_id
        except Exception as exc:
            alert.last_error = f"{type(exc).__name__}: {exc}"[:2000]
            if alert.attempt_count >= settings.alert_max_attempts:
                alert.status = "failed"
                alert.next_attempt_at = None
            else:
                alert.status = "retrying"
                delay_minutes = settings.alert_retry_base_minutes * (2 ** (alert.attempt_count - 1))
                alert.next_attempt_at = datetime.utcnow() + timedelta(minutes=delay_minutes)
    db.commit()
    for alert in alerts:
        db.refresh(alert)
    return alerts
