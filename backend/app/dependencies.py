from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .access_profile import has_country_access, parse_access_profile
from .database import get_db
from .models import User
from .radar_config import country_for_source
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
    return has_country_access(current_user.access_profile or "peru", country_for_source(source))


def require_source_access(current_user: User, source: str) -> None:
    if not source_is_allowed(current_user, source):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Este modulo no esta habilitado para tu perfil")


def source_access_condition(column, current_user: User):
    countries = parse_access_profile(current_user.access_profile or "peru") or {"peru"}
    if len(countries) >= 3:
        return None
    conditions = []
    if "chile" in countries:
        conditions.append(column.ilike("mercado_publico%"))
    if "argentina" in countries:
        conditions.append(column.ilike("comprar_argentina%"))
    if "peru" in countries:
        conditions.append(and_(~column.ilike("mercado_publico%"), ~column.ilike("comprar_argentina%")))
    return or_(*conditions)
