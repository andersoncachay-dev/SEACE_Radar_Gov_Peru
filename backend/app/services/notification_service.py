from __future__ import annotations

import smtplib
import re
from datetime import datetime, timedelta
from email.message import EmailMessage
from html import escape

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Alert, AlertRule, Opportunity, OpportunitySnapshot
from ..radar_config import country_for_source
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


def _format_amount(opportunity: Opportunity) -> str | None:
    amount = opportunity.amount or 0
    if amount <= 0:
        return None
    grouped = f"{amount:,.0f}"
    if country_for_source(opportunity.source) == "chile":
        return f"PESO CL {grouped.replace(',', '.')}"
    return f"S/ {grouped}"


def _format_datetime(value: datetime | None) -> str | None:
    return value.strftime("%d/%m/%Y %H:%M") if value else None


def _email_subject(opportunity: Opportunity | None) -> str:
    country_label = "Chile" if opportunity and country_for_source(opportunity.source) == "chile" else "Perú"
    return f"Rodar Consulting GovRadar · Nueva Alerta Gobierno {country_label}"


def _is_active_new_process(opportunity: Opportunity, now: datetime | None = None) -> bool:
    status = str(opportunity.status or "").strip().casefold()
    if any(label in status for label in ("culminado", "cerrado", "adjudicado", "revocado", "desierto")):
        return False
    deadline = _deadline_for(opportunity)
    return deadline is None or deadline > (now or datetime.utcnow())


def _build_message(opportunity: Opportunity, alert_type: str) -> str:
    alert_labels = {
        "new_process": "Nueva oportunidad detectada",
        "priority_match": "Oportunidad de alta prioridad",
        "deadline": "Vencimiento comercial próximo",
    }
    deadline_text = _format_datetime(_deadline_for(opportunity)) or "Sin fecha confirmada"
    publication_text = _format_datetime(opportunity.publication_date)
    amount_text = _format_amount(opportunity)
    lines = [
        f"GovRadar · {alert_labels.get(alert_type, 'Alerta de oportunidad')}\n",
        f"Nomenclatura: {opportunity.nomenclature or 'Sin nomenclatura'}",
        f"Entidad: {opportunity.entity or 'Sin entidad'}",
    ]
    if opportunity.object_type:
        lines.append(f"Objeto: {opportunity.object_type}")
    if opportunity.region:
        lines.append(f"Región: {opportunity.region}")
    lines.append(f"Prioridad: {opportunity.priority} · Score: {opportunity.score}")
    if amount_text:
        lines.append(f"Monto referencial: {amount_text}")
    if publication_text:
        lines.append(f"Fecha de publicación: {publication_text}")
    lines.append(f"Fecha límite: {deadline_text}")
    lines.append("")
    lines.append(f"Revisar oportunidad: {opportunity.detail_url or 'Disponible en GovRadar'}")
    return "\n".join(lines)


def _highlight_keywords_html(text: str, keywords: str) -> str:
    """Escape ``text`` for HTML and wrap whichever configured keywords it
    contains in an inline-styled <mark> - email clients ignore CSS classes,
    so the highlight style has to travel inline."""
    if not text:
        return ""
    terms: list[str] = []
    seen: set[str] = set()
    for raw in re.split(r"[,;\n]+", keywords or ""):
        term = raw.strip()
        if len(term) >= 3 and not term.isdigit() and term.casefold() not in seen:
            seen.add(term.casefold())
            terms.append(term)
    if not terms:
        return escape(text)
    terms.sort(key=len, reverse=True)
    pattern = re.compile(r"\b(" + "|".join(re.escape(term) for term in terms) + r")\b", re.IGNORECASE)
    parts = pattern.split(text)
    highlighted = []
    for index, part in enumerate(parts):
        if not part:
            continue
        if index % 2 == 1:
            highlighted.append(
                '<mark style="background:#fff1a8;color:#071f3f;font-weight:700;'
                f'padding:0 2px;border-radius:3px;">{escape(part)}</mark>'
            )
        else:
            highlighted.append(escape(part))
    return "".join(highlighted)


def _build_message_html(opportunity: Opportunity, alert_type: str, keywords: str = "") -> str:
    alert_labels = {
        "new_process": "Nueva oportunidad detectada",
        "priority_match": "Oportunidad de alta prioridad",
        "deadline": "Vencimiento comercial próximo",
    }
    deadline_text = _format_datetime(_deadline_for(opportunity)) or "Sin fecha confirmada"
    publication_text = _format_datetime(opportunity.publication_date)
    amount_text = _format_amount(opportunity)
    rows = [
        ("Nomenclatura", opportunity.nomenclature or "Sin nomenclatura"),
        ("Entidad", opportunity.entity or "Sin entidad"),
    ]
    if opportunity.object_type:
        rows.append(("Objeto", opportunity.object_type))
    if opportunity.region:
        rows.append(("Región", opportunity.region))
    rows.append(("Prioridad", f"{opportunity.priority or '-'} · Score: {opportunity.score}"))
    if amount_text:
        rows.append(("Monto referencial", amount_text))
    if publication_text:
        rows.append(("Fecha de publicación", publication_text))
    rows.append(("Fecha límite", deadline_text))
    row_html = [
        f"<p style=\"margin:0 0 10px;\"><strong>{escape(label)}:</strong> {escape(value)}</p>"
        for label, value in rows
    ]
    if opportunity.description:
        row_html.insert(
            2,
            f"<p style=\"margin:0 0 10px;\"><strong>Descripción:</strong> "
            f"{_highlight_keywords_html(opportunity.description, keywords)}</p>",
        )
    if row_html:
        row_html[-1] = row_html[-1].replace("margin:0 0 10px;", "margin:0;", 1)
    body_html = "".join(row_html)
    detail_url = opportunity.detail_url or ""
    return _branded_email_html(
        alert_labels.get(alert_type, "Alerta de oportunidad"),
        body_html,
        cta_url=detail_url or None,
        cta_label="Ver oportunidad" if detail_url else None,
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
        if not opp or opp.is_archived or not _is_active_new_process(opp):
            continue
        for rule in rules:
            if not _priority_at_least(opp.priority, rule.min_priority):
                continue
            if rule.country != "both" and rule.country != country_for_source(opp.source):
                continue
            searchable_text = " ".join((
                opp.nomenclature or "",
                opp.description or "",
                opp.entity or "",
                opp.object_type or "",
            ))
            if not _matches_rule_keywords(searchable_text, rule.keywords):
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


def _branded_email_html(title: str, body_html: str, cta_url: str | None = None, cta_label: str | None = None) -> str:
    """Wrap a notification's content in RODAR's branded HTML shell.

    Used for password recovery (and reusable for any future transactional
    email); logo is served by the frontend itself so it stays in sync with
    whatever FRONTEND_URL points at, instead of being hardcoded here.
    """
    logo_url = f"{settings.frontend_url}/assets/Rodarfondoblanco.png"
    cta_html = ""
    if cta_url and cta_label:
        cta_html = (
            '<div style="text-align:center;margin:28px 0 8px;">'
            f'<a href="{cta_url}" style="display:inline-block;background:#185bc1;color:#ffffff;'
            'padding:13px 28px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;">'
            f"{cta_label}</a></div>"
        )
    # Outlook desktop renders HTML email with Word's engine, which ignores
    # div max-width/margin:auto centering. A table with an explicit width
    # attribute (not just CSS) is the only layout Outlook reliably respects,
    # so the card stays a fixed 480px instead of stretching full window width.
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f7fc;">
      <tr>
        <td align="center" style="padding:32px 16px;">
          <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="width:480px;max-width:480px;background:#ffffff;border-radius:12px;border:1px solid #c8d8ee;font-family:Arial,Helvetica,sans-serif;">
            <tr>
              <td style="background:#185bc1;height:4px;line-height:4px;font-size:0;">&nbsp;</td>
            </tr>
            <tr>
              <td align="center" style="padding:22px 28px 16px;border-bottom:2px solid #185bc1;">
                <img src="{logo_url}" alt="RODAR Consulting" width="58" height="50" style="display:block;width:58px;height:50px;" />
              </td>
            </tr>
            <tr>
              <td style="padding:28px;color:#051326;">
                <h1 style="margin:0 0 16px;font-size:19px;color:#061a35;">{title}</h1>
                <div style="font-size:14.5px;line-height:1.6;color:#28374d;">{body_html}</div>
                {cta_html}
              </td>
            </tr>
            <tr>
              <td style="padding:22px 28px;background:#f3f7fc;border-top:1px solid #c8d8ee;border-radius:0 0 12px 12px;">
                <p style="margin:0;color:#51627b;font-size:11.5px;line-height:1.6;text-align:center;">RODAR Consulting S.A.C. &middot; Radar comercial para procesos de gobierno</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
    """


def _send_azure_email(
    destination: str, message: str, subject: str = "GovRadar · Nueva alerta comercial", html: str | None = None
) -> str:
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
            "html": html or "<br>".join(message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").splitlines()),
        },
    }
    result = client.begin_send(payload).result()
    status = result.get("status") if isinstance(result, dict) else getattr(result, "status", "")
    if str(status).lower() != "succeeded":
        raise RuntimeError(f"Azure Email devolvio estado {status or 'desconocido'}")
    return str(result.get("id", "") if isinstance(result, dict) else getattr(result, "id", ""))


def _send_smtp_email(
    destination: str, message: str, subject: str = "GovRadar - alerta de oportunidad", html: str | None = None
) -> str:
    if not settings.smtp_host or not settings.smtp_from:
        raise RuntimeError("SMTP no configurado. Definir SMTP_HOST y SMTP_FROM.")
    email = EmailMessage()
    email["Subject"] = subject
    email["From"] = settings.smtp_from
    email["To"] = destination
    email.set_content(message)
    if html:
        email.add_alternative(html, subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(email)
    return str(email.get("Message-ID") or "")


def _send_email(
    destination: str, message: str, subject: str = "GovRadar · Nueva alerta comercial", html: str | None = None
) -> str:
    if settings.email_provider == "azure":
        return _send_azure_email(destination, message, subject, html)
    return _send_smtp_email(destination, message, subject, html)


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
    stale_new_alerts = list(
        db.scalars(
            select(Alert).where(
                Alert.alert_type == "new_process",
                Alert.status.not_in(["sent", "skipped"]),
            )
        ).all()
    )
    for alert in stale_new_alerts:
        opportunity = db.get(Opportunity, alert.opportunity_id)
        if opportunity and not _is_active_new_process(opportunity, now):
            alert.status = "skipped"
            alert.last_error = "Proceso histórico o vencido; no corresponde a un lanzamiento nuevo"
            alert.next_attempt_at = None
    db.flush()
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
        opportunity = db.get(Opportunity, alert.opportunity_id)
        if opportunity and opportunity.is_archived:
            alert.status = "skipped"
            alert.last_error = "Proceso retirado por decisión comercial"
            alert.next_attempt_at = None
            continue
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
                html_body = _build_message_html(opportunity, alert.alert_type, rule.keywords) if opportunity else None
                provider_message_id = _send_email(
                    rule.destination, clean_message, subject=_email_subject(opportunity), html=html_body
                )
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
