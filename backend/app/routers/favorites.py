from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import User, UserFavorite
from ..services.favorite_service import FAVORITE_KINDS, add_favorite, list_favorites, remove_favorite

router = APIRouter(prefix="/favorites", tags=["favorites"])


class FavoriteIn(BaseModel):
    kind: str
    ref_key: str = Field(min_length=1, max_length=200)
    label: str = Field(default="", max_length=300)


class FavoriteOut(BaseModel):
    kind: str
    ref_key: str
    label: str
    created_at: datetime


def _check_kind(kind: str) -> None:
    if kind not in FAVORITE_KINDS:
        raise HTTPException(status_code=422, detail="Tipo de favorito no válido")


def _out(item: UserFavorite) -> FavoriteOut:
    return FavoriteOut(kind=item.kind, ref_key=item.ref_key, label=item.label, created_at=item.created_at)


@router.get("", response_model=list[FavoriteOut])
def get_favorites(kind: str | None = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if kind:
        _check_kind(kind)
    return [_out(item) for item in list_favorites(db, current_user.id, kind)]


@router.put("", response_model=FavoriteOut)
def put_favorite(payload: FavoriteIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_kind(payload.kind)
    return _out(add_favorite(db, current_user.id, payload.kind, payload.ref_key.strip(), payload.label.strip()))


@router.delete("", status_code=204)
def delete_favorite(kind: str, ref_key: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_kind(kind)
    remove_favorite(db, current_user.id, kind, ref_key)
