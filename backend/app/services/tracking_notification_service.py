from __future__ import annotations

import logging
from datetime import datetime, timedelta
from html import escape

from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    Opportunity,
    OpportunityTracking,
    OpportunityTrackingStage,
    TrackingResponsible,
    User,
)
from ..radar_config import country_for_source
from .notification_service import _branded_email_html, _send_email

logger = logging.getLogger(__name__)

TIME_ALERT_LABELS = {"atender": "ATENDER", "urgente": "URGENTE"}
TIME_ALERT_COLORS = {"atender": "#9a6b00", "urgente": "#b42318"}


def send_stage_support_request(
    db: Session,
    stage: OpportunityTrackingStage,
    opportunity: Opportunity,
    responsible_ids: list[int],
    message: str,
    owner_name: str,
) -> tuple[int, int]:
    """Manually triggered support request to specific responsables assigned to a stage.

    Only sends to responsables actually assigned to the stage (not the whole area) —
    the gestor picks who, one by one, from the assignee chips.
    """
    assigned_ids = {responsible.id for responsible in stage.assignees}
    target_ids = [rid for rid in responsible_ids if rid in assigned_ids]
    if not target_ids:
        return (0, 0)

    country_label = "Chile" if country_for_source(opportunity.source) == "chile" else "Perú"
    due_label = stage.due_date.strftime("%d/%m/%Y") if stage.due_date else "Por definir"
    subject = f"GovRadar · Solicitud de apoyo — {opportunity.nomenclature or opportunity.entity}"

    document_links_text = ""
    document_links_html = ""
    if opportunity.requirement_pdf_url:
        document_links_text += f"\nBases / requerimiento: {opportunity.requirement_pdf_url}"
        document_links_html += f'<p><a href="{opportunity.requirement_pdf_url}">Ver bases / requerimiento</a></p>'
    if opportunity.detail_url:
        document_links_text += f"\nPublicación original: {opportunity.detail_url}"
        document_links_html += f'<p><a href="{opportunity.detail_url}">Ver publicación original</a></p>'

    sent = 0
    failed = 0
    for responsible_id in target_ids:
        responsible = db.get(TrackingResponsible, responsible_id)
        if not responsible or not responsible.email:
            failed += 1
            continue

        custom_note_text = f"\n\nNota adicional:\n{message.strip()}" if message.strip() else ""
        custom_note_html = f"<p><strong>Nota adicional:</strong> {escape(message.strip())}</p>" if message.strip() else ""

        plain_message = (
            f"Buenas tardes {responsible.full_name},\n\n"
            f"Estamos participando en un proceso de contratación con el Estado de {country_label} y necesitamos tu apoyo "
            f"en la etapa \"{stage.name}\".\n\n"
            "Detalle de la oportunidad:\n"
            f"- Entidad: {opportunity.entity}\n"
            f"- Proceso: {opportunity.nomenclature}\n"
            f"- Descripción: {opportunity.description}\n"
            f"- Fecha límite de la etapa: {due_label}"
            f"{document_links_text}\n\n"
            f"{owner_name} es el responsable de este proceso y se pondrá en contacto contigo para coordinar los detalles."
            f"{custom_note_text}\n\n"
            "Gracias de antemano por tu apoyo.\n\n"
            "Saludos cordiales,\nEquipo GovRadar"
        )
        html_body = (
            f"<p>Buenas tardes {escape(responsible.full_name)},</p>"
            f"<p>Estamos participando en un proceso de contratación con el Estado de {country_label} y necesitamos tu apoyo "
            f"en la etapa <strong>{escape(stage.name)}</strong>.</p>"
            "<p><strong>Detalle de la oportunidad:</strong></p>"
            "<ul>"
            f"<li><strong>Entidad:</strong> {escape(opportunity.entity)}</li>"
            f"<li><strong>Proceso:</strong> {escape(opportunity.nomenclature)}</li>"
            f"<li><strong>Descripción:</strong> {escape(opportunity.description)}</li>"
            f"<li><strong>Fecha límite de la etapa:</strong> {due_label}</li>"
            "</ul>"
            f"{document_links_html}"
            f"<p><strong>{escape(owner_name)}</strong> es el responsable de este proceso y se pondrá en contacto contigo "
            "para coordinar los detalles.</p>"
            f"{custom_note_html}"
            "<p>Gracias de antemano por tu apoyo.</p>"
        )
        html = _branded_email_html("Solicitud de apoyo", html_body, cta_url=settings.frontend_url, cta_label="Ir a GovRadar")
        try:
            _send_email(responsible.email, plain_message, subject, html=html)
        except Exception:
            logger.exception("No se pudo enviar la solicitud de apoyo al responsable %s", responsible.id)
            failed += 1
        else:
            sent += 1

    return (sent, failed)


def _format_remaining(remaining: timedelta) -> str:
    total_seconds = max(0, int(remaining.total_seconds()))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    return f"{days} dd {hours} HH {minutes} MM"


def send_time_status_alert(
    db: Session,
    stage: OpportunityTrackingStage,
    opportunity: Opportunity,
    tracking: OpportunityTracking,
    tier: str,
    remaining: timedelta,
) -> tuple[int, int]:
    """Recordatorio automático al responsable y corresponsable cuando una etapa sin
    completar cruza el semáforo de tiempo a "Atender" o "Urgente". Se dispara desde
    tracking_service.evaluate_time_status_alerts, corriendo periódicamente vía el
    scheduler (ver scheduler_service.send_tracking_time_alerts_job)."""
    recipients: list[User] = []
    if tracking.started_by_id:
        owner = db.get(User, tracking.started_by_id)
        if owner:
            recipients.append(owner)
    if tracking.co_responsible_id and tracking.co_responsible_id != tracking.started_by_id:
        co_responsible = db.get(User, tracking.co_responsible_id)
        if co_responsible:
            recipients.append(co_responsible)
    if not recipients:
        return (0, 0)

    country_label = "Chile" if country_for_source(opportunity.source) == "chile" else "Perú"
    tier_label = TIME_ALERT_LABELS.get(tier, tier.upper())
    tier_color = TIME_ALERT_COLORS.get(tier, "#9a6b00")
    remaining_label = _format_remaining(remaining)
    subject = f"GovRadar · Alerta Recordatorio Oportunidad Pendiente de Gestión — {tier_label}"
    escalation_note = (
        "Si la etapa no pasa a Completado o Bloqueado, recibirás una nueva alerta cuando el tiempo restante baje a estado Urgente."
        if tier == "atender"
        else "La etapa sigue sin completarse y su tiempo restante es crítico."
    )

    sent = 0
    failed = 0
    for user in recipients:
        if not user.email:
            failed += 1
            continue
        plain_message = (
            f"Atención. Tenemos la oportunidad {opportunity.entity}, proceso {opportunity.nomenclature}, "
            f"gestionándose actualmente en la etapa \"{stage.name}\" ({country_label}) en estado \"{tier_label}\".\n\n"
            f"Tiempo restante: {remaining_label}\n\n"
            f"{escalation_note}\n\n"
            "Ingresa a GovRadar para gestionar la etapa."
        )
        html_body = (
            f"<p>Atención. Tenemos la oportunidad <strong>{escape(opportunity.entity)}</strong>, proceso "
            f"<strong>{escape(opportunity.nomenclature)}</strong>, gestionándose actualmente en la etapa "
            f"<strong>{escape(stage.name)}</strong> ({country_label}) en estado "
            f"<strong style=\"color:{tier_color}\">{tier_label}</strong>.</p>"
            f"<p><strong>Tiempo restante:</strong> {remaining_label}</p>"
            f"<p>{escape(escalation_note)}</p>"
        )
        html = _branded_email_html(
            "Alerta Recordatorio Oportunidad Pendiente de Gestión",
            html_body,
            cta_url=settings.frontend_url,
            cta_label="Ir a GovRadar",
        )
        try:
            _send_email(user.email, plain_message, subject, html=html)
        except Exception:
            logger.exception("No se pudo enviar la alerta de tiempo (%s) al usuario %s", tier, user.id)
            failed += 1
        else:
            sent += 1

    return (sent, failed)


def send_opportunity_date_change_alert(
    db: Session,
    tracking: OpportunityTracking,
    opportunity: Opportunity,
    changes: list[dict],
) -> tuple[int, int]:
    """Aviso al responsable y corresponsable cuando la verificación automática detecta
    que el portal (SEACE/Mercado Público) cambió alguna fecha oficial de un proceso en
    seguimiento activo -algo frecuente en Fin de Consultas o Fin de Propuesta."""
    if not changes:
        return (0, 0)
    recipients: list[User] = []
    if tracking.started_by_id:
        owner = db.get(User, tracking.started_by_id)
        if owner:
            recipients.append(owner)
    if tracking.co_responsible_id and tracking.co_responsible_id != tracking.started_by_id:
        co_responsible = db.get(User, tracking.co_responsible_id)
        if co_responsible:
            recipients.append(co_responsible)
    if not recipients:
        return (0, 0)

    country_label = "Chile" if country_for_source(opportunity.source) == "chile" else "Perú"
    portal_label = "Mercado Público" if country_label == "Chile" else "SEACE"
    subject = f"GovRadar · Cambio de fecha detectado — {opportunity.nomenclature or opportunity.entity}"

    def _fmt(value: datetime | None) -> str:
        return value.strftime("%d/%m/%Y %H:%M") if value else "Sin fecha"

    changes_text = "\n".join(f"- {item['label']}: {_fmt(item['old'])} -> {_fmt(item['new'])}" for item in changes)
    changes_html = "".join(
        f"<li><strong>{escape(item['label'])}:</strong> {_fmt(item['old'])} &rarr; <strong>{_fmt(item['new'])}</strong></li>"
        for item in changes
    )

    sent = 0
    failed = 0
    for user in recipients:
        if not user.email:
            failed += 1
            continue
        plain_message = (
            f"Se detectó un cambio de fecha en el proceso {opportunity.nomenclature} de {opportunity.entity} "
            f"({country_label}), verificado directamente en {portal_label}.\n\n"
            f"{changes_text}\n\n"
            "Revisamos automáticamente el portal mientras el proceso siga vigente; las etapas de Cotización "
            "aún no completadas ya se reajustaron a las nuevas fechas.\n\n"
            "Ingresa a GovRadar para revisar el detalle."
        )
        html_body = (
            f"<p>Se detectó un cambio de fecha en el proceso <strong>{escape(opportunity.nomenclature)}</strong> de "
            f"<strong>{escape(opportunity.entity)}</strong> ({country_label}), verificado directamente en {portal_label}.</p>"
            f"<ul>{changes_html}</ul>"
            "<p>Revisamos automáticamente el portal mientras el proceso siga vigente; las etapas de Cotización "
            "aún no completadas ya se reajustaron a las nuevas fechas.</p>"
        )
        html = _branded_email_html(
            "Cambio de fecha detectado", html_body, cta_url=settings.frontend_url, cta_label="Ir a GovRadar"
        )
        try:
            _send_email(user.email, plain_message, subject, html=html)
        except Exception:
            logger.exception("No se pudo enviar la alerta de cambio de fecha al usuario %s", user.id)
            failed += 1
        else:
            sent += 1

    return (sent, failed)
