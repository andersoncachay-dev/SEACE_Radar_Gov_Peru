from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Opportunity, OpportunitySnapshot
from .entity_catalog_service import find_entity


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
    if isinstance(value, (datetime, pd.Timestamp)):
        parsed = pd.Timestamp(value)
    else:
        text = str(value).strip()
        year_first = bool(re.match(r"^\d{4}-\d{2}-\d{2}(?:[T\s]|$)", text))
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=not year_first)
    if pd.isna(parsed):
        return None
    if getattr(parsed, "tzinfo", None) is not None:
        parsed = parsed.tz_convert("UTC").tz_localize(None)
    return parsed.to_pydatetime()


def _merge_datetime(existing: datetime | None, value: Any) -> datetime | None:
    parsed = _as_datetime(value)
    return parsed if parsed is not None else existing


def _first_text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _as_text(row.get(key))
        if value:
            return value
    return ""


def _content_hash(row: dict[str, Any]) -> str:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def upsert_opportunities(db: Session, rows: pd.DataFrame, source: str, run_id: int | None = None) -> int:
    count = 0
    if rows is None or rows.empty:
        return count

    for _, raw in rows.iterrows():
        row = raw.to_dict()
        external_id = _first_text(row, "nomenclatura", "codigo", "Nomenclatura")
        if not external_id:
            continue
        archive_country = "chile" if source.lower().startswith("mercado_publico") else "peru"
        archive_key = external_id.casefold()
        archived_id = db.scalar(
            select(Opportunity.id).where(
                Opportunity.is_archived.is_(True),
                Opportunity.archive_country == archive_country,
                Opportunity.archive_key == archive_key,
            ).limit(1)
        )
        if archived_id is not None:
            # Los retiros son decisiones comerciales persistentes. Una nueva
            # lectura de la fuente no debe reincorporar ni modificar el proceso.
            continue
        existing = db.scalar(select(Opportunity).where(Opportunity.source == source, Opportunity.external_id == external_id))
        opportunity = existing or Opportunity(source=source, external_id=external_id)
        previous_hash = opportunity.content_hash if existing else ""

        incoming_entity = _first_text(row, "entidad", "Nombre o Sigla de la Entidad")
        incoming_nomenclature = _first_text(row, "nomenclatura", "codigo", "Nomenclatura")
        incoming_object_type = _first_text(row, "objeto", "Objeto de Contratacion", "Objeto de Contratación")
        incoming_description = _first_text(row, "descripcion", "Descripcion de Objeto", "Descripción de Objeto")
        opportunity.entity = incoming_entity or (opportunity.entity if existing else "")
        opportunity.nomenclature = incoming_nomenclature or (opportunity.nomenclature if existing else external_id)
        opportunity.object_type = incoming_object_type or (opportunity.object_type if existing else "")
        opportunity.description = incoming_description or (opportunity.description if existing else "")
        catalog_entity = find_entity(opportunity.entity)
        previous_region = opportunity.region if existing else ""
        opportunity.region = (
            _first_text(row, "region", "Departamento", "Región")
            or (catalog_entity or {}).get("region", "")
            or (opportunity.region if existing else "")
        )
        if opportunity.region.strip().casefold() == "chile" and previous_region.strip().casefold() not in ("", "chile"):
            opportunity.region = previous_region
        opportunity.buyer_ruc = (
            _first_text(row, "ruc", "RUC")
            or (catalog_entity or {}).get("ruc", "")
            or (opportunity.buyer_ruc if existing else "")
        )
        opportunity.ocid = _as_text(row.get("ocid")) or (opportunity.ocid if existing else "")
        opportunity.tender_id = _as_text(row.get("tender_id")) or (opportunity.tender_id if existing else "")
        opportunity.ocds_source_id = _as_text(row.get("source_id")) or (opportunity.ocds_source_id if existing else "")
        opportunity.release_id = _as_text(row.get("release_id")) or (opportunity.release_id if existing else "")
        documents_payload = _as_text(row.get("documentos_ocds"))
        if documents_payload:
            try:
                parsed_documents = json.loads(documents_payload)
                opportunity.documents_count = len(parsed_documents) if isinstance(parsed_documents, list) else 0
            except json.JSONDecodeError:
                opportunity.documents_count = 0
        elif not existing:
            opportunity.documents_count = 0
        incoming_amount = _as_float(
            row.get("monto")
            or row.get("VR / VE / Cuantia de la contratacion")
            or row.get("VR / VE / Cuantía de la contratación")
        )
        # Result listings do not expose the amount. Preserve a value previously
        # collected from the detail page when a later lightweight scan returns 0.
        if incoming_amount > 0 or not existing:
            opportunity.amount = incoming_amount
        incoming_currency = _first_text(row, "moneda", "Moneda")
        opportunity.currency = incoming_currency or (opportunity.currency if existing else "")
        incoming_status = _first_text(row, "estado_operativo", "estado_comercial", "Estado Comercial")
        incoming_schedule_source = _first_text(row, "schedule_source")
        # A lightweight OCDS refresh deliberately says that its schedule is
        # pending. It must not downgrade a schedule already validated in SEACE.
        if existing and opportunity.schedule_source == "seace" and not incoming_schedule_source:
            if "revisar cronograma seace" in incoming_status.casefold():
                incoming_status = ""
        if not incoming_status and not existing:
            proposal_deadline = _as_datetime(row.get("propuesta_fin"))
            incoming_status = "Vigente para Propuesta" if proposal_deadline is None or proposal_deadline > datetime.utcnow() else "Proceso Culminado"
        opportunity.status = incoming_status or (opportunity.status if existing else "Vigente para Propuesta")
        incoming_priority = _first_text(row, "prioridad")
        opportunity.priority = incoming_priority or (opportunity.priority if existing else "C")
        incoming_score = _as_text(row.get("score"))
        if incoming_score or not existing:
            opportunity.score = int(_as_float(incoming_score))
        incoming_reasons = _as_text(row.get("motivos_score"))
        opportunity.reasons = incoming_reasons or (opportunity.reasons if existing else "")
        incoming_detail_url = _first_text(row, "url_detalle", "detalle_url")
        incoming_pdf_url = _as_text(row.get("requerimiento_pdf"))
        incoming_pdf_local = _as_text(row.get("requerimiento_pdf_local"))
        opportunity.detail_url = incoming_detail_url or (opportunity.detail_url if existing else "")
        opportunity.requirement_pdf_url = incoming_pdf_url or (opportunity.requirement_pdf_url if existing else "")
        opportunity.requirement_pdf_local = incoming_pdf_local or (opportunity.requirement_pdf_local if existing else "")
        opportunity.publication_date = _merge_datetime(
            opportunity.publication_date,
            row.get("fecha_publicacion") or row.get("Fecha y Hora de Publicacion") or row.get("Fecha y Hora de Publicación"),
        )
        replace_schedule = str(row.get("replace_schedule", "")).strip().lower() in {"true", "1", "yes"}
        if replace_schedule:
            opportunity.consultation_deadline = _as_datetime(row.get("consulta_fin"))
            opportunity.quote_deadline = _as_datetime(row.get("cotizacion_fin"))
            opportunity.proposal_deadline = _as_datetime(row.get("propuesta_fin"))
        else:
            opportunity.consultation_deadline = _merge_datetime(opportunity.consultation_deadline, row.get("consulta_fin"))
            opportunity.quote_deadline = _merge_datetime(opportunity.quote_deadline, row.get("cotizacion_fin"))
            opportunity.proposal_deadline = _merge_datetime(opportunity.proposal_deadline, row.get("propuesta_fin"))
        if incoming_schedule_source == "seace":
            opportunity.schedule_source = "seace"
            opportunity.schedule_validated_at = _as_datetime(row.get("schedule_validated_at")) or datetime.utcnow()
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
