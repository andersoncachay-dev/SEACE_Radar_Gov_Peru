from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user, require_admin
from ..models import TrackingPhase, TrackingStageTemplate, TrackingStageTemplateArea, User
from ..schemas import (
    TrackingPhaseOut,
    TrackingStageTemplateCreate,
    TrackingStageTemplateOut,
    TrackingStageTemplateReorderIn,
    TrackingStageTemplateUpdate,
)

router = APIRouter(prefix="/tracking-templates", tags=["tracking"])


def _set_template_areas(db: Session, template: TrackingStageTemplate, area_ids: list[int]) -> None:
    db.execute(delete(TrackingStageTemplateArea).where(TrackingStageTemplateArea.stage_template_id == template.id))
    for area_id in area_ids:
        db.add(TrackingStageTemplateArea(stage_template_id=template.id, area_id=area_id))


@router.get("/phases", response_model=list[TrackingPhaseOut])
def list_phases(country: str | None = None, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = select(TrackingPhase).where(TrackingPhase.is_active.is_(True))
    if country:
        query = query.where(TrackingPhase.country == country)
    return list(db.scalars(query.order_by(TrackingPhase.sort_order)).all())


@router.get("/phases/{phase_id}/stages", response_model=list[TrackingStageTemplateOut])
def list_stage_templates(phase_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return list(
        db.scalars(
            select(TrackingStageTemplate)
            .where(TrackingStageTemplate.phase_id == phase_id, TrackingStageTemplate.is_active.is_(True))
            .order_by(TrackingStageTemplate.sort_order)
        ).all()
    )


@router.post("/phases/{phase_id}/stages", response_model=TrackingStageTemplateOut, status_code=status.HTTP_201_CREATED)
def create_stage_template(
    phase_id: int,
    payload: TrackingStageTemplateCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    phase = db.get(TrackingPhase, phase_id)
    if not phase:
        raise HTTPException(status_code=404, detail="Fase no encontrada")
    template = TrackingStageTemplate(
        phase_id=phase_id,
        name=payload.name.strip(),
        sort_order=payload.sort_order,
        is_outcome_step=payload.is_outcome_step,
        is_informational=payload.is_informational,
        default_duration_days=payload.default_duration_days,
        created_by_id=current_user.id,
        updated_by_id=current_user.id,
    )
    db.add(template)
    db.flush()
    _set_template_areas(db, template, payload.area_ids)
    db.commit()
    db.refresh(template)
    return template


@router.patch("/stages/{stage_template_id}", response_model=TrackingStageTemplateOut)
def update_stage_template(
    stage_template_id: int,
    payload: TrackingStageTemplateUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    template = db.get(TrackingStageTemplate, stage_template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Etapa no encontrada")
    if payload.name is not None:
        template.name = payload.name.strip()
    if payload.sort_order is not None:
        template.sort_order = payload.sort_order
    if payload.is_active is not None:
        template.is_active = payload.is_active
    if payload.is_outcome_step is not None:
        template.is_outcome_step = payload.is_outcome_step
    if payload.is_informational is not None:
        template.is_informational = payload.is_informational
    if payload.default_duration_days is not None:
        template.default_duration_days = payload.default_duration_days
    if payload.area_ids is not None:
        _set_template_areas(db, template, payload.area_ids)
    template.updated_by_id = current_user.id
    db.commit()
    db.refresh(template)
    return template


@router.post("/stages/reorder", response_model=list[TrackingStageTemplateOut])
def reorder_stage_templates(
    payload: TrackingStageTemplateReorderIn,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    templates_by_id = {
        t.id: t
        for t in db.scalars(
            select(TrackingStageTemplate).where(TrackingStageTemplate.id.in_(payload.ordered_stage_template_ids))
        )
    }
    for index, template_id in enumerate(payload.ordered_stage_template_ids):
        template = templates_by_id.get(template_id)
        if template:
            template.sort_order = index
    db.commit()
    return list(
        db.scalars(
            select(TrackingStageTemplate)
            .where(TrackingStageTemplate.id.in_(payload.ordered_stage_template_ids))
            .order_by(TrackingStageTemplate.sort_order)
        ).all()
    )


@router.delete("/stages/{stage_template_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_stage_template(stage_template_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    template = db.get(TrackingStageTemplate, stage_template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Etapa no encontrada")
    template.is_active = False
    db.commit()
