from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user, require_admin
from ..models import TrackingArea, TrackingAreaResponsible, TrackingResponsible, User
from ..schemas import TrackingResponsibleCreate, TrackingResponsibleOut, TrackingResponsibleUpdate

router = APIRouter(prefix="/tracking-responsibles", tags=["tracking"])


def _validate_area_ids(db: Session, area_ids: list[int]) -> None:
    existing = list(db.scalars(select(TrackingArea.id).where(TrackingArea.id.in_(area_ids))))
    if len(existing) != len(set(area_ids)):
        raise HTTPException(status_code=422, detail="Alguna de las areas no existe")


def _set_areas(db: Session, responsible: TrackingResponsible, area_ids: list[int]) -> None:
    db.execute(delete(TrackingAreaResponsible).where(TrackingAreaResponsible.responsible_id == responsible.id))
    for area_id in area_ids:
        db.add(TrackingAreaResponsible(area_id=area_id, responsible_id=responsible.id))


@router.get("", response_model=list[TrackingResponsibleOut])
def list_tracking_responsibles(
    area_id: int | None = None,
    country: str | None = None,
    active_only: bool = True,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = select(TrackingResponsible)
    if active_only:
        query = query.where(TrackingResponsible.is_active.is_(True))
    if country:
        query = query.where(TrackingResponsible.country_scope.in_([country, "ambos"]))
    responsibles = list(db.scalars(query.order_by(TrackingResponsible.full_name)).all())
    if area_id:
        responsible_ids = set(
            db.scalars(select(TrackingAreaResponsible.responsible_id).where(TrackingAreaResponsible.area_id == area_id))
        )
        responsibles = [r for r in responsibles if r.id in responsible_ids]
    return responsibles


@router.post("", response_model=TrackingResponsibleOut, status_code=status.HTTP_201_CREATED)
def create_tracking_responsible(
    payload: TrackingResponsibleCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)
):
    _validate_area_ids(db, payload.area_ids)
    responsible = TrackingResponsible(
        full_name=payload.full_name.strip(),
        email=str(payload.email).strip().lower(),
        country_scope=payload.country_scope,
        is_active=payload.is_active,
    )
    db.add(responsible)
    db.flush()
    _set_areas(db, responsible, payload.area_ids)
    db.commit()
    db.refresh(responsible)
    return responsible


@router.patch("/{responsible_id}", response_model=TrackingResponsibleOut)
def update_tracking_responsible(
    responsible_id: int,
    payload: TrackingResponsibleUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    responsible = db.get(TrackingResponsible, responsible_id)
    if not responsible:
        raise HTTPException(status_code=404, detail="Responsable no encontrado")
    if payload.full_name is not None:
        responsible.full_name = payload.full_name.strip()
    if payload.email is not None:
        responsible.email = str(payload.email).strip().lower()
    if payload.country_scope is not None:
        responsible.country_scope = payload.country_scope
    if payload.is_active is not None:
        responsible.is_active = payload.is_active
    if payload.area_ids is not None:
        _validate_area_ids(db, payload.area_ids)
        _set_areas(db, responsible, payload.area_ids)
    db.commit()
    db.refresh(responsible)
    return responsible
