from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    Opportunity,
    OpportunityTracking,
    OpportunityTrackingStage,
    OpportunityTrackingStageArea,
    OpportunityTrackingStageAssignee,
    TrackingAreaResponsible,
    TrackingPhase,
    TrackingResponsible,
    TrackingStageTemplate,
    TrackingStageTemplateArea,
    User,
)
from ..radar_config import country_for_source
from .tracking_notification_service import send_time_status_alert

PHASE_COTIZACION = "cotizacion"
PHASE_PERFECCIONAMIENTO = "perfeccionamiento_contrato"
PHASE_IMPLEMENTACION = "implementacion"


def phase_by_key(db: Session, key: str, country: str) -> TrackingPhase:
    phase = db.scalar(select(TrackingPhase).where(TrackingPhase.key == key, TrackingPhase.country == country))
    if not phase:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Fase '{key}' no configurada para {country}")
    return phase


def active_templates_for_phase(db: Session, phase_id: int) -> list[TrackingStageTemplate]:
    return list(
        db.scalars(
            select(TrackingStageTemplate)
            .where(TrackingStageTemplate.phase_id == phase_id, TrackingStageTemplate.is_active.is_(True))
            .order_by(TrackingStageTemplate.sort_order)
        )
    )


def resolve_default_assignees(db: Session, area_ids: list[int], country: str) -> dict[int, list[TrackingResponsible]]:
    """Map each area id to its active responsibles scoped to the opportunity's country."""
    result: dict[int, list[TrackingResponsible]] = {area_id: [] for area_id in area_ids}
    if not area_ids:
        return result
    rows = db.execute(
        select(TrackingAreaResponsible.area_id, TrackingResponsible)
        .join(TrackingResponsible, TrackingResponsible.id == TrackingAreaResponsible.responsible_id)
        .where(
            TrackingAreaResponsible.area_id.in_(area_ids),
            TrackingResponsible.is_active.is_(True),
            TrackingResponsible.country_scope.in_([country, "ambos"]),
        )
    ).all()
    for area_id, responsible in rows:
        result[area_id].append(responsible)
    return result


def _instantiate_stage(
    db: Session,
    tracking: OpportunityTracking,
    phase: TrackingPhase,
    template: TrackingStageTemplate,
    opportunity: Opportunity,
    auto_due_date: datetime | None = None,
) -> OpportunityTrackingStage:
    due_date = auto_due_date
    if due_date is None and template.default_duration_days:
        due_date = datetime.utcnow() + timedelta(days=template.default_duration_days)
    stage = OpportunityTrackingStage(
        tracking_id=tracking.id,
        phase_id=phase.id,
        stage_template_id=template.id,
        name=template.name,
        sort_order=template.sort_order,
        is_outcome_step=template.is_outcome_step,
        is_informational=template.is_informational,
        due_date=due_date,
    )
    db.add(stage)
    db.flush()

    template_area_ids = list(
        db.scalars(select(TrackingStageTemplateArea.area_id).where(TrackingStageTemplateArea.stage_template_id == template.id))
    )
    for area_id in template_area_ids:
        db.add(OpportunityTrackingStageArea(stage_id=stage.id, area_id=area_id))

    # Nota: la asignación por defecto NO dispara correo automático -solo el botón
    # manual "Enviar alerta" (StageSupportButton) notifica- para no llenar de spam la
    # bandeja de los responsables cada vez que arranca un seguimiento o se abre una fase.
    country = country_for_source(opportunity.source)
    assignees_by_area = resolve_default_assignees(db, template_area_ids, country)
    seen_responsible_ids: set[int] = set()
    for area_id, responsibles in assignees_by_area.items():
        for responsible in responsibles:
            if responsible.id in seen_responsible_ids:
                continue
            seen_responsible_ids.add(responsible.id)
            db.add(
                OpportunityTrackingStageAssignee(
                    stage_id=stage.id,
                    responsible_id=responsible.id,
                    area_id=area_id,
                    is_default=True,
                )
            )
    db.flush()

    return stage


def compute_cotizacion_due_dates(
    templates: list[TrackingStageTemplate],
    tracking_started_at: datetime | None,
    consultation_deadline: datetime | None,
    proposal_deadline: datetime | None,
) -> dict[int, datetime]:
    """Ancla cada etapa de Cotización a su fecha oficial real cuando existe, en vez de
    estimarla con un porcentaje: Consultas -> consultation_deadline real (SEACE/Mercado
    Público), Envío de Propuesta -> proposal_deadline/quote_deadline real, Registro de
    participación -> fecha de inicio del seguimiento. Cualquier etapa intermedia sin
    fecha oficial propia (ej. "Cotización", la preparación interna de la oferta) se
    reparte dentro de la ventana entre la última ancla conocida y el cierre de
    propuesta, terminando siempre 1 día antes de ese cierre. Las etapas informativas
    (ej. "Otorgamiento de la Buena Pro") quedan fuera de este reparto -su fecha viene
    directamente del cronograma SEACE vía tracking_date_refresh_service, no de aquí."""
    non_outcome = [t for t in templates if not t.is_outcome_step and not t.is_informational]
    if not non_outcome:
        return {}
    ordered = sorted(non_outcome, key=lambda t: t.sort_order)

    due_dates: dict[int, datetime] = {}
    if tracking_started_at is not None:
        due_dates[ordered[0].id] = tracking_started_at

    consultas_template = next((t for t in ordered if "consulta" in t.name.strip().lower()), None)
    if consultas_template and consultation_deadline is not None:
        due_dates[consultas_template.id] = consultation_deadline

    last_template = ordered[-1]
    if proposal_deadline is not None:
        due_dates[last_template.id] = proposal_deadline

        window_end = proposal_deadline - timedelta(days=1)
        window_start = due_dates.get(consultas_template.id) if consultas_template else None
        if window_start is None:
            window_start = tracking_started_at
        pending = [t for t in ordered if t.id not in due_dates]
        if pending:
            if window_start is not None and window_end > window_start:
                total_seconds = (window_end - window_start).total_seconds()
                share = total_seconds / len(pending)
                for index, template in enumerate(pending, start=1):
                    due_dates[template.id] = window_start + timedelta(seconds=share * index)
            else:
                for template in pending:
                    due_dates[template.id] = window_end

    return due_dates


def reanchor_cotizacion_due_dates(db: Session, tracking: OpportunityTracking, opportunity: Opportunity) -> bool:
    """Recomputa las fechas de las etapas de Cotización aún no completadas con las
    fechas oficiales actuales de la oportunidad -por si el portal las cambió luego de
    haber iniciado el seguimiento- reutilizando la misma ancla que compute_cotizacion_due_dates.
    No toca etapas ya completadas. Devuelve True si alguna fecha cambió realmente."""
    country = country_for_source(opportunity.source)
    phase = phase_by_key(db, PHASE_COTIZACION, country)
    stages = list(
        db.scalars(
            select(OpportunityTrackingStage).where(
                OpportunityTrackingStage.tracking_id == tracking.id,
                OpportunityTrackingStage.phase_id == phase.id,
                OpportunityTrackingStage.completed.is_(False),
                OpportunityTrackingStage.is_outcome_step.is_(False),
                OpportunityTrackingStage.is_informational.is_(False),
            )
        )
    )
    if not stages:
        return False
    templates = active_templates_for_phase(db, phase.id)
    proposal_deadline = opportunity.proposal_deadline or opportunity.quote_deadline
    due_dates_by_template_id = compute_cotizacion_due_dates(
        templates, tracking.started_at, opportunity.consultation_deadline, proposal_deadline
    )
    changed = False
    for stage in stages:
        if stage.stage_template_id is None:
            continue
        new_due_date = due_dates_by_template_id.get(stage.stage_template_id)
        if new_due_date is not None and new_due_date != stage.due_date:
            stage.due_date = new_due_date
            changed = True
    return changed


def _seed_phase_stages(db: Session, tracking: OpportunityTracking, phase: TrackingPhase, opportunity: Opportunity) -> None:
    already_started = db.scalar(
        select(OpportunityTrackingStage.id).where(
            OpportunityTrackingStage.tracking_id == tracking.id,
            OpportunityTrackingStage.phase_id == phase.id,
        )
    )
    if already_started:
        return
    templates = active_templates_for_phase(db, phase.id)

    due_dates_by_template_id: dict[int, datetime] = {}
    if phase.key == PHASE_COTIZACION:
        proposal_deadline = opportunity.proposal_deadline or opportunity.quote_deadline
        due_dates_by_template_id = compute_cotizacion_due_dates(
            templates, tracking.started_at, opportunity.consultation_deadline, proposal_deadline
        )

    for template in templates:
        auto_due_date = due_dates_by_template_id.get(template.id)
        _instantiate_stage(db, tracking, phase, template, opportunity, auto_due_date)


def get_tracking_for_opportunity(db: Session, opportunity_id: int) -> OpportunityTracking | None:
    return db.scalar(select(OpportunityTracking).where(OpportunityTracking.opportunity_id == opportunity_id))


def start_tracking(db: Session, opportunity: Opportunity, current_user: User) -> OpportunityTracking:
    existing = get_tracking_for_opportunity(db, opportunity.id)
    if existing:
        if existing.status == "retirado":
            # Re-sending a previously withdrawn opportunity just reactivates
            # its existing history instead of silently doing nothing.
            existing.status = "active"
            db.commit()
            db.refresh(existing)
        return existing

    country = country_for_source(opportunity.source)
    phase = phase_by_key(db, PHASE_COTIZACION, country)
    tracking = OpportunityTracking(
        opportunity_id=opportunity.id,
        current_phase_id=phase.id,
        started_at=datetime.utcnow(),
        started_by_id=current_user.id,
    )
    db.add(tracking)
    db.flush()

    _seed_phase_stages(db, tracking, phase, opportunity)

    db.commit()
    db.refresh(tracking)
    return tracking


def set_quotation_outcome(
    db: Session, tracking: OpportunityTracking, opportunity: Opportunity, outcome: str, current_user: User
) -> OpportunityTracking:
    country = country_for_source(opportunity.source)
    cotizacion_phase = phase_by_key(db, PHASE_COTIZACION, country)
    outcome_stage = db.scalar(
        select(OpportunityTrackingStage).where(
            OpportunityTrackingStage.tracking_id == tracking.id,
            OpportunityTrackingStage.phase_id == cotizacion_phase.id,
            OpportunityTrackingStage.is_outcome_step.is_(True),
        )
    )
    if not outcome_stage:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Etapa de resultado no encontrada")

    outcome_stage.outcome = outcome
    outcome_stage.completed = outcome != "pendiente"
    outcome_stage.completed_at = datetime.utcnow() if outcome != "pendiente" else None
    outcome_stage.completed_by_id = current_user.id if outcome != "pendiente" else None
    outcome_stage.status = "completado" if outcome != "pendiente" else "pendiente"

    tracking.quotation_outcome = outcome
    tracking.quotation_outcome_at = datetime.utcnow()
    tracking.quotation_outcome_by_id = current_user.id

    if outcome == "ganado":
        next_phase = phase_by_key(db, PHASE_PERFECCIONAMIENTO, country)
        _seed_phase_stages(db, tracking, next_phase, opportunity)
        tracking.current_phase_id = next_phase.id
    else:
        # Perdido/Pendiente bloquean las fases siguientes -incluso si ya se habían
        # sembrado por un resultado "Ganado" anterior que el gestor corrigió.
        tracking.current_phase_id = cotizacion_phase.id

    db.commit()
    db.refresh(tracking)
    return tracking


def advance_phase(db: Session, tracking: OpportunityTracking, opportunity: Opportunity, current_user: User) -> OpportunityTracking:
    current_phase = db.get(TrackingPhase, tracking.current_phase_id) if tracking.current_phase_id else None
    if not current_phase or current_phase.key != PHASE_PERFECCIONAMIENTO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Solo se puede avanzar manualmente desde Perfeccionamiento de Contrato",
        )

    pending = db.scalar(
        select(OpportunityTrackingStage.id).where(
            OpportunityTrackingStage.tracking_id == tracking.id,
            OpportunityTrackingStage.phase_id == current_phase.id,
            OpportunityTrackingStage.completed.is_(False),
        )
    )
    if pending:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Todas las etapas de la fase actual deben estar completadas")

    next_phase = phase_by_key(db, PHASE_IMPLEMENTACION, country_for_source(opportunity.source))
    _seed_phase_stages(db, tracking, next_phase, opportunity)
    tracking.current_phase_id = next_phase.id

    db.commit()
    db.refresh(tracking)
    return tracking


def toggle_stage(db: Session, stage: OpportunityTrackingStage, updates: dict, current_user: User) -> OpportunityTrackingStage:
    if "due_date" in updates:
        stage.due_date = updates["due_date"]
    if "status" in updates and updates["status"] is not None:
        stage.status = updates["status"]
    if "alert_atender_enabled" in updates and updates["alert_atender_enabled"] is not None:
        stage.alert_atender_enabled = updates["alert_atender_enabled"]
    if "alert_urgente_enabled" in updates and updates["alert_urgente_enabled"] is not None:
        stage.alert_urgente_enabled = updates["alert_urgente_enabled"]
    if "completed" in updates and updates["completed"] is not None:
        completed = updates["completed"]
        stage.completed = completed
        stage.completed_at = datetime.utcnow() if completed else None
        stage.completed_by_id = current_user.id if completed else None
        if completed and stage.status == "pendiente":
            stage.status = "completado"
        elif not completed and stage.status == "completado":
            stage.status = "pendiente"
    db.commit()
    db.refresh(stage)
    return stage


def update_stage_areas(db: Session, stage: OpportunityTrackingStage, area_ids: list[int]) -> OpportunityTrackingStage:
    db.execute(delete(OpportunityTrackingStageArea).where(OpportunityTrackingStageArea.stage_id == stage.id))
    for area_id in area_ids:
        db.add(OpportunityTrackingStageArea(stage_id=stage.id, area_id=area_id))
    db.commit()
    db.refresh(stage)
    return stage


def update_stage_assignees(
    db: Session,
    stage: OpportunityTrackingStage,
    responsible_ids: list[int],
    _opportunity: Opportunity,
    current_user: User,
) -> OpportunityTrackingStage:
    # Nota: reasignar responsables NO dispara correo automático -solo el botón manual
    # "Enviar alerta" notifica- para no llenar de spam la bandeja de los responsables.
    existing = list(
        db.scalars(select(OpportunityTrackingStageAssignee).where(OpportunityTrackingStageAssignee.stage_id == stage.id))
    )
    existing_ids = {row.responsible_id for row in existing}
    target_ids = set(responsible_ids)

    for row in existing:
        if row.responsible_id not in target_ids:
            db.delete(row)

    for responsible_id in target_ids - existing_ids:
        db.add(
            OpportunityTrackingStageAssignee(
                stage_id=stage.id,
                responsible_id=responsible_id,
                assigned_by_id=current_user.id,
                is_default=False,
            )
        )

    db.flush()

    db.commit()
    db.refresh(stage)
    return stage


def _stage_time_status(due_date: datetime | None, window_start: datetime | None, now: datetime) -> str | None:
    """Mirrors the frontend's computeTimeStatus: percentage of the stage's own time
    window (window_start -> due_date) still remaining right now."""
    if not due_date or not window_start:
        return None
    total_seconds = (due_date - window_start).total_seconds()
    if total_seconds <= 0:
        return None
    if now > due_date:
        return "vencido"
    remaining_pct = (due_date - now).total_seconds() / total_seconds * 100
    if remaining_pct >= 80:
        return "on_time"
    if remaining_pct >= 40:
        return "atender"
    return "urgente"


def evaluate_time_status_alerts(db: Session) -> dict[str, int]:
    """Escanea las etapas activas y no completadas, calcula su semáforo de tiempo
    igual que el frontend, y dispara un correo al owner + corresponsable la primera
    vez que cruzan a "Atender" o a "Urgente" -respetando los switches por etapa y sin
    reenviar en cada corrida gracias al ratchet en last_time_alert_status. Se ejecuta
    periódicamente desde scheduler_service.send_tracking_time_alerts_job."""
    now = datetime.utcnow()
    summary = {"sent": 0, "failed": 0}
    cotizacion_phase_ids: dict[str, int] = {}

    trackings = list(db.scalars(select(OpportunityTracking).where(OpportunityTracking.status == "active")))
    for tracking in trackings:
        opportunity = db.get(Opportunity, tracking.opportunity_id)
        if not opportunity:
            continue
        country = country_for_source(opportunity.source)
        if country not in cotizacion_phase_ids:
            cotizacion_phase_ids[country] = phase_by_key(db, PHASE_COTIZACION, country).id
        cotizacion_phase_id = cotizacion_phase_ids[country]

        stages = list(
            db.scalars(
                select(OpportunityTrackingStage)
                .where(OpportunityTrackingStage.tracking_id == tracking.id)
                .order_by(OpportunityTrackingStage.phase_id, OpportunityTrackingStage.sort_order)
            )
        )
        by_phase: dict[int, list[OpportunityTrackingStage]] = {}
        for stage in stages:
            by_phase.setdefault(stage.phase_id, []).append(stage)

        for phase_id, phase_stages in by_phase.items():
            ordered = sorted(phase_stages, key=lambda s: s.sort_order)
            previous_due = opportunity.publication_date if phase_id == cotizacion_phase_id else None
            for stage in ordered:
                window_start = previous_due
                previous_due = stage.due_date
                if stage.is_outcome_step or stage.completed:
                    continue
                tier = _stage_time_status(stage.due_date, window_start, now)
                if tier in (None, "on_time"):
                    if stage.last_time_alert_status:
                        stage.last_time_alert_status = ""
                    continue
                if tier == "vencido":
                    continue

                should_alert = (
                    tier == "atender"
                    and stage.alert_atender_enabled
                    and stage.last_time_alert_status not in ("atender", "urgente")
                ) or (tier == "urgente" and stage.alert_urgente_enabled and stage.last_time_alert_status != "urgente")
                if not should_alert:
                    continue

                sent, failed = send_time_status_alert(db, stage, opportunity, tracking, tier, stage.due_date - now)
                stage.last_time_alert_status = tier
                summary["sent"] += sent
                summary["failed"] += failed

    db.commit()
    return summary
