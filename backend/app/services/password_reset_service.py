from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from html import escape
from urllib.parse import urlencode

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..models import PasswordResetToken, User
from ..security import hash_password
from .notification_service import _branded_email_html, _send_email

logger = logging.getLogger(__name__)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def request_password_reset(db: Session, email: str) -> None:
    user = db.scalar(select(User).where(User.email == email.strip().lower(), User.is_active.is_(True)))
    if not user:
        return

    now = datetime.utcnow()
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    raw_token = secrets.token_urlsafe(48)
    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=_token_hash(raw_token),
        expires_at=now + timedelta(minutes=settings.password_reset_minutes),
    )
    db.add(reset_token)
    db.commit()

    reset_url = f"{settings.frontend_url}/?{urlencode({'reset_token': raw_token})}"
    display_name = user.first_name or user.full_name
    message = (
        f"Hola {display_name},\n\n"
        "Recibimos una solicitud para cambiar la contraseña de tu cuenta GovRadar.\n\n"
        f"Crear nueva contraseña: {reset_url}\n\n"
        f"Este enlace vence en {settings.password_reset_minutes} minutos y solo puede usarse una vez. "
        "Si no solicitaste el cambio, puedes ignorar este correo."
    )
    html_body = (
        f"<p>Hola {escape(display_name)},</p>"
        "<p>Recibimos una solicitud para cambiar la contraseña de tu cuenta GovRadar.</p>"
        f"<p>Este enlace vence en {settings.password_reset_minutes} minutos y solo puede usarse una vez. "
        "Si no solicitaste el cambio, puedes ignorar este correo.</p>"
    )
    html = _branded_email_html(
        "Recuperación de contraseña", html_body, cta_url=reset_url, cta_label="Crear nueva contraseña"
    )
    try:
        _send_email(user.email, message, "GovRadar · Recuperación de contraseña", html=html)
    except Exception:
        logger.exception("No se pudo enviar el correo de recuperación para el usuario %s", user.id)
        reset_token.used_at = datetime.utcnow()
        db.commit()


def reset_password(db: Session, raw_token: str, password: str) -> bool:
    now = datetime.utcnow()
    reset_token = db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == _token_hash(raw_token),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
    )
    if not reset_token:
        return False
    user = db.get(User, reset_token.user_id)
    if not user or not user.is_active:
        return False

    user.password_hash = hash_password(password)
    reset_token.used_at = now
    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.id != reset_token.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    db.commit()
    return True
