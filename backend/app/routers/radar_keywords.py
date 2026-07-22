from __future__ import annotations

import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user, require_admin
from ..models import RadarKeyword, User
from ..schemas import RadarKeywordCreate, RadarKeywordOut

router = APIRouter(prefix="/radar-keywords", tags=["radar keywords"])


def _country(value: str) -> str:
    country = value.strip().lower()
    if country not in {"peru", "chile"}:
        raise HTTPException(status_code=404, detail="País no disponible")
    return country


def _require_country_access(user: User, country: str) -> None:
    if user.access_profile not in {country, "both"}:
        raise HTTPException(status_code=403, detail="Este país no está habilitado para tu perfil")


def _normalize(value: str) -> str:
    plain = unicodedata.normalize("NFD", value.strip().lower())
    plain = "".join(char for char in plain if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", plain)


@router.get("/{country}", response_model=list[RadarKeywordOut])
def list_keywords(country: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    normalized_country = _country(country)
    _require_country_access(current_user, normalized_country)
    items = list(
        db.scalars(
            select(RadarKeyword)
            .where(RadarKeyword.country == normalized_country)
            .order_by(RadarKeyword.created_at.asc(), RadarKeyword.id.asc())
        ).all()
    )
    return [RadarKeywordOut(id=item.id, country=item.country, keyword=item.keyword) for item in items]


@router.post("/{country}", response_model=RadarKeywordOut, status_code=status.HTTP_201_CREATED)
def create_keyword(
    country: str,
    payload: RadarKeywordCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized_country = _country(country)
    _require_country_access(current_user, normalized_country)
    keyword = re.sub(r"\s+", " ", payload.keyword.strip())
    normalized_keyword = _normalize(keyword)
    if len(normalized_keyword) < 2 or not any(char.isalpha() for char in normalized_keyword):
        raise HTTPException(status_code=422, detail="Ingresa una palabra o frase válida")
    item = RadarKeyword(
        country=normalized_country,
        keyword=keyword,
        normalized_keyword=normalized_keyword,
        created_by_id=current_user.id,
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="La palabra ya está configurada para este país") from None
    db.refresh(item)
    return RadarKeywordOut(id=item.id, country=item.country, keyword=item.keyword)


@router.delete("/{country}/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_keyword(
    country: str,
    keyword_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized_country = _country(country)
    _require_country_access(current_user, normalized_country)
    item = db.scalar(
        select(RadarKeyword).where(RadarKeyword.id == keyword_id, RadarKeyword.country == normalized_country)
    )
    if not item:
        raise HTTPException(status_code=404, detail="Palabra personalizada no encontrada")
    db.delete(item)
    db.commit()
    return None
