from __future__ import annotations

import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user, require_admin
from ..models import TrackingArea, User
from ..schemas import TrackingAreaCreate, TrackingAreaOut, TrackingAreaUpdate

router = APIRouter(prefix="/tracking-areas", tags=["tracking"])


def _slugify(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
    return slug or "area"


def _unique_key(db: Session, name: str) -> str:
    base_key = _slugify(name)[:32]
    key = base_key
    suffix = 2
    while db.scalar(select(TrackingArea.id).where(TrackingArea.key == key)) is not None:
        key = f"{base_key}_{suffix}"[:40]
        suffix += 1
    return key


@router.get("", response_model=list[TrackingAreaOut])
def list_tracking_areas(
    active_only: bool = True,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = select(TrackingArea)
    if active_only:
        query = query.where(TrackingArea.is_active.is_(True))
    return list(db.scalars(query.order_by(TrackingArea.sort_order)).all())


@router.post("", response_model=TrackingAreaOut, status_code=201)
def create_tracking_area(payload: TrackingAreaCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    name = payload.name.strip()
    existing = db.scalar(select(TrackingArea).where(TrackingArea.name.ilike(name)))
    if existing:
        raise HTTPException(status_code=409, detail="Ya existe un área con ese nombre")
    area = TrackingArea(key=_unique_key(db, name), name=name, sort_order=payload.sort_order, is_active=True)
    db.add(area)
    db.commit()
    db.refresh(area)
    return area


@router.patch("/{area_id}", response_model=TrackingAreaOut)
def update_tracking_area(
    area_id: int,
    payload: TrackingAreaUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    area = db.get(TrackingArea, area_id)
    if not area:
        raise HTTPException(status_code=404, detail="Área no encontrada")
    if payload.name is not None:
        name = payload.name.strip()
        existing = db.scalar(select(TrackingArea).where(TrackingArea.name.ilike(name), TrackingArea.id != area_id))
        if existing:
            raise HTTPException(status_code=409, detail="Ya existe un área con ese nombre")
        area.name = name
    if payload.sort_order is not None:
        area.sort_order = payload.sort_order
    if payload.is_active is not None:
        area.is_active = payload.is_active
    db.commit()
    db.refresh(area)
    return area
