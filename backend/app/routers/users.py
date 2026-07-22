from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user, require_admin
from ..models import User
from ..schemas import AssignableUserOut, UserCreate, UserOut, UserUpdate
from ..security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/assignable", response_model=list[AssignableUserOut])
def list_assignable_users(
    country: str | None = None,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = select(User).where(User.is_active.is_(True))
    if country in {"peru", "chile"}:
        query = query.where(User.access_profile.in_([country, "both"]))
    users = list(db.scalars(query.order_by(User.full_name)).all())
    return [AssignableUserOut(id=user.id, full_name=user.full_name, access_profile=user.access_profile) for user in users]


def _normalize_phone(value: str, country_code: str, country_name: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith(country_code) and len(digits) > 9:
        digits = digits[len(country_code):]
    if not digits:
        return ""
    if len(digits) != 9:
        raise HTTPException(status_code=422, detail=f"El celular de {country_name} debe contener 9 dígitos")
    return f"+{country_code}{digits}"


@router.get("", response_model=list[UserOut])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return list(db.scalars(select(User).order_by(User.created_at.desc())).all())


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    normalized_email = str(payload.email).strip().lower()
    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=normalized_email,
        full_name=f"{payload.first_name.strip()} {payload.last_name.strip()}",
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        position=payload.position.strip(),
        address=payload.address.strip(),
        phone_peru=_normalize_phone(payload.phone_peru, "51", "Peru"),
        phone_chile=_normalize_phone(payload.phone_chile, "56", "Chile"),
        access_profile=payload.access_profile,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.email is not None:
        normalized_email = str(payload.email).strip().lower()
        existing = db.scalar(select(User).where(User.email == normalized_email, User.id != user_id))
        if existing:
            raise HTTPException(status_code=409, detail="El correo ya esta registrado")
        user.email = normalized_email
    for field in ["first_name", "last_name", "position", "address", "access_profile", "role", "is_active"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(user, field, value.strip() if isinstance(value, str) else value)
    if payload.phone_peru is not None:
        user.phone_peru = _normalize_phone(payload.phone_peru, "51", "Peru")
    if payload.phone_chile is not None:
        user.phone_chile = _normalize_phone(payload.phone_chile, "56", "Chile")
    contact_changed = payload.access_profile is not None or payload.phone_peru is not None or payload.phone_chile is not None
    if contact_changed and user.access_profile in {"peru", "both"} and not user.phone_peru.strip():
        raise HTTPException(status_code=422, detail="El celular de Peru es obligatorio para este perfil")
    if contact_changed and user.access_profile in {"chile", "both"} and not user.phone_chile.strip():
        raise HTTPException(status_code=422, detail="El celular de Chile es obligatorio para este perfil")
    user.full_name = f"{user.first_name} {user.last_name}".strip() or user.full_name
    if payload.password:
        user.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(user)
    return user
