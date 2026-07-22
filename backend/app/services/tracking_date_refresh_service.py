from __future__ import annotations

import json
import logging
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AppSetting, Opportunity, OpportunityTracking, OpportunityTrackingStage
from ..radar_config import country_for_source
from .ingestion_service import _as_datetime
from .tracking_notification_service import send_opportunity_date_change_alert
from .tracking_service import reanchor_cotizacion_due_dates

logger = logging.getLogger(__name__)

SUPPORTED_COUNTRIES = ("peru", "chile")

DATE_FIELDS = ("consultation_deadline", "quote_deadline", "proposal_deadline")
DATE_FIELD_LABELS = {
    "consultation_deadline": "Fin de Consultas",
    "quote_deadline": "Fin de Cotización",
    "proposal_deadline": "Fin de Propuesta",
}

# Etapas informativas de Perú (no requieren gestión propia, solo trazabilidad):
# el nombre debe calzar exacto con INFORMATIONAL_STAGES en la migracion
# 20260722_0031_seace_informational_stages, que las siembra. La columna viene del
# cronograma completo que ya trae src.seace_browser_scraper.
INFORMATIONAL_STAGE_FIELDS = {
    "Absolución de Consultas y Observaciones": "absolucion_fin",
    "Integración de las Bases": "integracion_fin",
    "Calificación y Evaluación de Propuestas": "evaluacion_fin",
    "Otorgamiento de la Buena Pro": "buena_pro_fin",
}


def _interval_key(country: str) -> str:
    return f"tracking.date_refresh.{country}.interval_seconds"


def _last_run_key(country: str) -> str:
    return f"tracking.date_refresh.{country}.last_result"


def _schedule_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _write_setting(db: Session, key: str, value: str, user_id: int | None = None) -> None:
    item = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if item is None:
        db.add(AppSetting(key=key, value=value, updated_by_id=user_id))
    else:
        item.value = value
        item.updated_by_id = user_id


def get_date_refresh_interval_seconds(db: Session, country: str) -> int:
    item = db.scalar(select(AppSetting).where(AppSetting.key == _interval_key(country)))
    default_seconds = max(60, settings.tracking_date_refresh_interval_minutes * 60)
    if item is None:
        return default_seconds
    try:
        return max(60, int(item.value))
    except (TypeError, ValueError):
        return default_seconds


def save_date_refresh_interval_seconds(db: Session, country: str, interval_seconds: int, user_id: int | None) -> int:
    interval_seconds = max(60, int(interval_seconds))
    _write_setting(db, _interval_key(country), str(interval_seconds), user_id)
    db.commit()
    return interval_seconds


def get_last_date_refresh_result(db: Session, country: str) -> dict | None:
    item = db.scalar(select(AppSetting).where(AppSetting.key == _last_run_key(country)))
    if item is None:
        return None
    try:
        return json.loads(item.value)
    except (TypeError, ValueError):
        return None


def _save_last_run(db: Session, country: str, result: dict) -> None:
    _write_setting(db, _last_run_key(country), json.dumps(result, ensure_ascii=False))
    db.commit()


def _active_pending_trackings(db: Session, country: str) -> list[tuple[OpportunityTracking, Opportunity]]:
    """Trackings activos de un país cuya fecha de fin de propuesta/cotización aún no
    vence (o no se conoce todavía) - los únicos que tiene sentido re-verificar contra
    el portal."""
    now = datetime.utcnow()
    rows = db.execute(
        select(OpportunityTracking, Opportunity).join(Opportunity, Opportunity.id == OpportunityTracking.opportunity_id).where(
            OpportunityTracking.status == "active"
        )
    ).all()
    pending = []
    for tracking, opportunity in rows:
        if country_for_source(opportunity.source) != country:
            continue
        deadline = opportunity.proposal_deadline or opportunity.quote_deadline
        if deadline is None or deadline > now:
            pending.append((tracking, opportunity))
    return pending


def _diff_dates(opportunity: Opportunity, incoming: dict[str, datetime | None]) -> list[dict]:
    changes = []
    for field in DATE_FIELDS:
        new_value = incoming.get(field)
        if new_value is None:
            continue
        old_value = getattr(opportunity, field)
        if old_value is None or abs((old_value - new_value).total_seconds()) >= 60:
            changes.append({"field": field, "label": DATE_FIELD_LABELS[field], "old": old_value, "new": new_value})
    return changes


def _diff_informational_stages(db: Session, tracking: OpportunityTracking, row) -> list[dict]:
    """Revalida las etapas informativas del cronograma SEACE (Absolución de Consultas,
    Integración de las Bases, Calificación y Evaluación, Otorgamiento de la Buena Pro):
    no hay gestión comercial que hacer en ellas, solo dejar trazabilidad de sus fechas
    reales según el portal. Actualiza due_date directo en la etapa -no son columnas de
    Opportunity- y devuelve el mismo formato de "changes" que _diff_dates para que
    fluyan por el mismo camino de alertas/UI."""
    stages = db.scalars(
        select(OpportunityTrackingStage).where(
            OpportunityTrackingStage.tracking_id == tracking.id,
            OpportunityTrackingStage.is_informational.is_(True),
            OpportunityTrackingStage.name.in_(INFORMATIONAL_STAGE_FIELDS.keys()),
        )
    ).all()
    changes = []
    for stage in stages:
        field = INFORMATIONAL_STAGE_FIELDS.get(stage.name)
        if not field:
            continue
        new_value = _as_datetime(row.get(field))
        if new_value is None:
            continue
        old_value = stage.due_date
        if old_value is None or abs((old_value - new_value).total_seconds()) >= 60:
            changes.append({"field": f"stage:{stage.id}", "label": stage.name, "old": old_value, "new": new_value})
            stage.due_date = new_value
    return changes


def _refresh_peru(db: Session, items: list[tuple[OpportunityTracking, Opportunity]]) -> dict[int, list[dict]]:
    from src.seace_browser_scraper import search_seace_public_browser_targets

    targets = []
    for _tracking, opportunity in items:
        if not opportunity.nomenclature:
            continue
        year_match = re.search(r"-(20\d{2})-", opportunity.nomenclature)
        targets.append(
            {
                "nomenclature": opportunity.nomenclature,
                "keyword": (opportunity.description or opportunity.nomenclature)[:250],
                "year": year_match.group(1) if year_match else str(datetime.utcnow().year),
            }
        )
    if not targets:
        return {}
    seace_raw, _diagnostics = search_seace_public_browser_targets(targets, version="Seace 3", headless=True)
    if seace_raw is None or seace_raw.empty:
        return {}
    by_key = {
        _schedule_key(row.get("Nomenclatura", "")): row
        for _, row in seace_raw.iterrows()
        if _schedule_key(row.get("Nomenclatura", ""))
    }
    changes_by_opportunity: dict[int, list[dict]] = {}
    for tracking, opportunity in items:
        row = by_key.get(_schedule_key(opportunity.nomenclature))
        if row is None:
            continue
        incoming = {
            "consultation_deadline": _as_datetime(row.get("consulta_fin")),
            "quote_deadline": _as_datetime(row.get("cotizacion_fin")),
            "proposal_deadline": _as_datetime(row.get("propuesta_fin")),
        }
        changes = _diff_dates(opportunity, incoming)
        for change in changes:
            setattr(opportunity, change["field"], change["new"])
        stage_changes = _diff_informational_stages(db, tracking, row)
        all_changes = changes + stage_changes
        if all_changes:
            # Marca el cronograma como validado directamente en SEACE, igual que hace
            # el enriquecimiento de detalle del scheduler automático - así una corrida
            # OCDS posterior (menos confiable para estas fechas) no la vuelve a pisar.
            opportunity.schedule_source = "seace"
            opportunity.schedule_validated_at = datetime.utcnow()
            changes_by_opportunity[opportunity.id] = all_changes
    return changes_by_opportunity


def _refresh_chile(items: list[tuple[OpportunityTracking, Opportunity]]) -> dict[int, list[dict]]:
    import pandas as pd
    from src.mercado_publico_scraper import search_mercado_publico_details_by_code
    from src.normalizer import normalize_columns

    nomenclatures = [opportunity.nomenclature for _tracking, opportunity in items if opportunity.nomenclature]
    if not nomenclatures:
        return {}
    detail_rows, _diagnostics = search_mercado_publico_details_by_code(nomenclatures, headless=True)
    if not detail_rows:
        return {}
    normalized = normalize_columns(pd.DataFrame(detail_rows))
    if normalized is None or normalized.empty:
        return {}
    by_key: dict[str, object] = {}
    for _, row in normalized.iterrows():
        key = _schedule_key(row.get("nomenclatura") or row.get("Nomenclatura") or "")
        if key:
            by_key[key] = row
    changes_by_opportunity: dict[int, list[dict]] = {}
    for _tracking, opportunity in items:
        row = by_key.get(_schedule_key(opportunity.nomenclature))
        if row is None:
            continue
        incoming = {
            "consultation_deadline": _as_datetime(row.get("consulta_fin")),
            "quote_deadline": _as_datetime(row.get("cotizacion_fin")),
            "proposal_deadline": _as_datetime(row.get("propuesta_fin")),
        }
        changes = _diff_dates(opportunity, incoming)
        if changes:
            for change in changes:
                setattr(opportunity, change["field"], change["new"])
            changes_by_opportunity[opportunity.id] = changes
    return changes_by_opportunity


def refresh_active_opportunity_dates(db: Session, country: str) -> dict:
    """Re-consulta SEACE (Perú) o Mercado Público (Chile) para cada oportunidad activa
    en seguimiento de ese país cuya fecha de propuesta aún no vence -las entidades
    suelen mover el Fin de Consultas o el Fin de Propuesta/Buena Pro después de
    publicar-. Si algo cambió: guarda la nueva fecha, reancla las etapas de
    Cotización aún no completadas y avisa por correo al responsable y corresponsable.
    Corre periódicamente desde el scheduler, con un intervalo independiente por país
    (ver scheduler_service.refresh_tracking_dates_job)."""
    result: dict = {"ran_at": datetime.utcnow().isoformat(), "checked": 0, "changed": [], "errors": 0}
    try:
        pending = _active_pending_trackings(db, country)
        result["checked"] = len(pending)
        if not pending:
            _save_last_run(db, country, result)
            return result

        try:
            changes_by_opportunity = _refresh_peru(db, pending) if country == "peru" else _refresh_chile(pending)
        except Exception:
            logger.exception("Fallo al revalidar fechas de oportunidades de %s", country)
            changes_by_opportunity = {}
            result["errors"] += 1

        now = datetime.utcnow()
        for tracking, opportunity in pending:
            changes = changes_by_opportunity.get(opportunity.id)
            if not changes:
                continue
            reanchor_cotizacion_due_dates(db, tracking, opportunity)
            # Una fecha nueva que ya vencio al momento de detectarla no es gestionable
            # por correo -queda igual reflejada en la plataforma, pero no tiene sentido
            # avisar de una accion que ya no se puede tomar.
            actionable_changes = [change for change in changes if change["new"] >= now]
            sent, failed = (
                send_opportunity_date_change_alert(db, tracking, opportunity, actionable_changes)
                if actionable_changes
                else (0, 0)
            )
            result["changed"].append(
                {
                    "opportunity_id": opportunity.id,
                    "entity": opportunity.entity,
                    "nomenclature": opportunity.nomenclature,
                    "changes": [
                        {
                            "field": item["field"],
                            "label": item["label"],
                            "old": item["old"].isoformat() if item["old"] else None,
                            "new": item["new"].isoformat() if item["new"] else None,
                        }
                        for item in changes
                    ],
                    "alerts_sent": sent,
                    "alerts_failed": failed,
                }
            )

        db.commit()
    except Exception:
        logger.exception("Fallo inesperado en refresh_active_opportunity_dates (%s)", country)
        result["errors"] += 1

    _save_last_run(db, country, result)
    return result
