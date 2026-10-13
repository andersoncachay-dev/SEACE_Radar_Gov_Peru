"""Histórico Perú emails: weekly digest and "manual upload needed" notice."""
from __future__ import annotations

import html
import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import settings
from ...models import HistAlert, HistImportRun, User
from ...module_access import has_module_access
from ..notification_service import _branded_email_html, _send_email
from . import conosce
from .alerts_service import PRIORITY_LABELS, get_preference, matches_preference

logger = logging.getLogger(__name__)


def _module_users(db: Session) -> list[User]:
    users = db.scalars(select(User).where(User.is_active.is_(True))).all()
    return [user for user in users if user.role == "admin" or has_module_access(user.module_access, "historico_peru")]


def digest_recipients(db: Session) -> list[User]:
    return [user for user in _module_users(db) if user.historico_digest]


def admin_recipients(db: Session) -> list[User]:
    return [user for user in _module_users(db) if user.role == "admin"]


def _money(value: float) -> str:
    return f"S/ {value:,.0f}".replace(",", " ")


def build_digest(db: Session, today: date, user: User | None = None) -> tuple[str, str, str] | None:
    """Weekly digest; with a user, only the alerts matching their preferences."""
    week_ago = today - timedelta(days=7)
    preference = get_preference(db, user.id) if user else None
    active = [
        alert for alert in db.scalars(select(HistAlert).where(HistAlert.is_active.is_(True), HistAlert.status != "descartada")).all()
        if matches_preference(alert, preference)
    ]
    urgent = sorted((a for a in active if a.priority in ("P1", "P2")), key=lambda a: (a.priority, -a.score))
    new_this_week = [a for a in active if a.created_at.date() >= week_ago]
    expiring_90 = [a for a in active if a.kind == "vencimiento" and a.due_date and (a.due_date - today).days <= 90]
    if not urgent and not new_this_week:
        return None
    latest = db.scalar(select(HistImportRun).where(HistImportRun.status == "completed").order_by(HistImportRun.finished_at.desc()).limit(1))
    data_line = f"Datos CONOSCE al {latest.data_cut_date:%d/%m/%Y}." if latest and latest.data_cut_date else "Aún no hay una actualización completada."
    rows = "".join(
        f"<tr><td style='padding:6px 8px;border-bottom:1px solid #e3ebf6'><strong>{PRIORITY_LABELS.get(a.priority, a.priority)}</strong></td>"
        f"<td style='padding:6px 8px;border-bottom:1px solid #e3ebf6'>{html.escape(a.title)}<br><span style='color:#51627b'>{html.escape(a.entity_name)} · {html.escape(a.department)}</span></td>"
        f"<td style='padding:6px 8px;border-bottom:1px solid #e3ebf6;text-align:right;white-space:nowrap'>{_money(a.amount) if a.amount else ''}</td></tr>"
        for a in urgent[:15]
    )
    body = (
        f"<p>{len(urgent)} alertas críticas o altas, {len(new_this_week)} nuevas esta semana y "
        f"{len(expiring_90)} contratos que vencen en 90 días o menos.</p>"
        f"<table style='border-collapse:collapse;width:100%;font-size:14px'>{rows}</table>"
        f"<p style='color:#51627b'>{data_line}</p>"
    )
    text = "\n".join(f"[{PRIORITY_LABELS.get(a.priority)}] {a.title} — {a.entity_name}" for a in urgent[:15])
    subject = f"Histórico Perú · {len(urgent)} alertas prioritarias esta semana"
    return subject, text, _branded_email_html("Resumen semanal de alertas", body, f"{settings.frontend_url}/", "Abrir el centro de alertas")


def send_digest(db: Session, today: date) -> int:
    sent = 0
    for user in digest_recipients(db):
        content = build_digest(db, today, user)
        if content is None:
            continue
        subject, text, body_html = content
        try:
            _send_email(user.email, text, subject, body_html)
            sent += 1
        except Exception:
            logger.exception("Histórico digest to %s failed", user.email)
    return sent


def send_manual_upload_notice(db: Session, reason: str) -> int:
    files = [source for source in conosce.catalogue(date.today()) if source.dataset != "ordenes"][:8]
    links = "".join(f"<li><a href='{source.url}'>{html.escape(source.filename)}</a></li>" for source in files)
    body = (
        f"<p>La actualización automática de Histórico Perú no se completó: {html.escape(reason)}</p>"
        "<p>Descarga los archivos del mes desde CONOSCE (Datos Abiertos) y súbelos en "
        "<strong>Sistema › Histórico Perú › Cargar archivos</strong>. Las órdenes de compra son un archivo por mes.</p>"
        f"<ul>{links}</ul>"
    )
    subject = "Histórico Perú · Carga manual requerida"
    text = f"La actualización automática de Histórico Perú falló ({reason}). Sube los archivos de CONOSCE en Sistema › Histórico Perú."
    sent = 0
    for user in admin_recipients(db):
        try:
            _send_email(user.email, text, subject, _branded_email_html(subject, body, f"{settings.frontend_url}/", "Ir a GovRadar"))
            sent += 1
        except Exception:
            logger.exception("Histórico manual-upload notice to %s failed", user.email)
    return sent
