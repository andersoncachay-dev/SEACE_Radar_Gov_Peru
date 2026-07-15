from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import MessageOut, PasswordResetConfirm, PasswordResetRequest, TokenOut, UserOut
from ..dependencies import get_current_user
from ..security import create_access_token, verify_password
from ..services.password_reset_service import request_password_reset, reset_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == form.username.strip().lower(), User.is_active.is_(True)))
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenOut(access_token=create_access_token(user.email))


@router.post("/forgot-password", response_model=MessageOut)
def forgot_password(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    request_password_reset(db, str(payload.email))
    return MessageOut(message="Si el correo está registrado, recibirás un enlace para crear una nueva contraseña.")


@router.post("/reset-password", response_model=MessageOut)
def confirm_password_reset(payload: PasswordResetConfirm, db: Session = Depends(get_db)):
    if not reset_password(db, payload.token, payload.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El enlace no es válido o ya venció. Solicita uno nuevo.",
        )
    return MessageOut(message="Contraseña actualizada. Ya puedes iniciar sesión.")


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
