from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Opportunity, OpportunitySnapshot


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _as_float(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", ""))
    except Exception:
        return 0.0


def _as_datetime(value: Any) -> datetime | None:
    if value is None or _as_text(value) == "":
        return None
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def _merge_datetime(existing: datetime | None, value: Any) -> datetime | None:
    parsed = _as_datetime(value)
    return parsed if parsed is not None else existing


def _content_hash(row: dict[str, Any]) -> str:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def upsert_opportunities(db: Session, rows: pd.DataFrame, source: str, run_id: int | None = None) -> int:
    count = 0
    if rows is None or rows.empty:
        return count

    for _, raw in rows.iterrows():
        row = raw.to_dict()
        external_id = _as_text(row.get("nomenclatura") or row.get("codigo") or row.get("Nomenclatura"))
        if not external_id:
            continue
        existing = db.scalar(select(Opportunity).where(Opportunity.source == source, Opportunity.external_id == external_id))
        opportunity = existing or Opportunity(source=source, external_id=external_id)
        previous_hash = opportunity.content_hash if existing else ""

        opportunity.entity = _as_text(row.get("entidad") or row.get("Nombre o Sigla de la Entidad"))
        opportunity.nomenclature = _as_text(row.get("nomenclatura") or row.get("codigo") or row.get("Nomenclatura"))
        opportunity.object_type = _as_text(row.get("objeto") or row.get("Objeto de Contratación"))
        opportunity.description = _as_text(row.get("descripcion") or row.get("Descripción de Objeto"))
        opportunity.region = _as_text(row.get("region"))
        opportunity.amount = _as_float(row.get("monto") or row.get("VR / VE / Cuantía de la contratación"))
        opportunity.currency = _as_text(row.get("moneda") or row.get("Moneda"))
        opportunity.status = _as_text(row.get("estado_operativo") or row.get("estado_comercial") or row.get("Estado Comercial"))
        opportunity.priority = _as_text(row.get("prioridad") or "C")
        opportunity.score = int(_as_float(row.get("score")))
        opportunity.reasons = _as_text(row.get("motivos_score"))
        opportunity.detail_url = _as_text(row.get("url_detalle") or row.get("detalle_url"))
        opportunity.requirement_pdf_url = _as_text(row.get("requerimiento_pdf"))
        opportunity.requirement_pdf_local = _as_text(row.get("requerimiento_pdf_local"))
        opportunity.publication_date = _merge_datetime(
            opportunity.publication_date,
            row.get("fecha_publicacion") or row.get("Fecha y Hora de Publicacion"),
        )
        opportunity.consultation_deadline = _merge_datetime(opportunity.consultation_deadline, row.get("consulta_fin"))
        opportunity.quote_deadline = _merge_datetime(opportunity.quote_deadline, row.get("cotizacion_fin"))
        opportunity.proposal_deadline = _merge_datetime(opportunity.proposal_deadline, row.get("propuesta_fin"))
        current_hash = _content_hash(row)
        opportunity.content_hash = current_hash

        if not existing:
            db.add(opportunity)
            db.flush()
        if previous_hash != current_hash:
            db.add(
                OpportunitySnapshot(
                    opportunity_id=opportunity.id,
                    run_id=run_id,
                    previous_hash=previous_hash,
                    content_hash=current_hash,
                    change_type="created" if not previous_hash else "changed",
                    raw_payload=json.dumps(row, ensure_ascii=False, default=str),
                )
            )
        elif run_id is not None:
            db.add(
                OpportunitySnapshot(
                    opportunity_id=opportunity.id,
                    run_id=run_id,
                    previous_hash=previous_hash,
                    content_hash=current_hash,
                    change_type="seen",
                    raw_payload=json.dumps(row, ensure_ascii=False, default=str),
                )
            )
        count += 1
    db.commit()
    return count
