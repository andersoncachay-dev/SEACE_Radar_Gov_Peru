from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import parse_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    email = parse_access_token(token)
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or missing user")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required")
    return current_user


def source_is_allowed(current_user: User, source: str) -> bool:
    profile = current_user.access_profile or "peru"
    is_chile = str(source or "").lower().startswith("mercado_publico")
    return profile == "both" or (profile == "chile" and is_chile) or (profile == "peru" and not is_chile)


def require_source_access(current_user: User, source: str) -> None:
    if not source_is_allowed(current_user, source):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Este modulo no esta habilitado para tu perfil")


def source_access_condition(column, current_user: User):
    profile = current_user.access_profile or "peru"
    if profile == "both":
        return None
    chile_condition = column.ilike("mercado_publico%")
    return chile_condition if profile == "chile" else ~chile_condition
