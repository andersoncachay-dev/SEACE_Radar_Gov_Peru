from __future__ import annotations

import hashlib
import json
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
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        return None
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

        opportunity.entity = _first_text(row, "entidad", "Nombre o Sigla de la Entidad")
        opportunity.nomenclature = _first_text(row, "nomenclatura", "codigo", "Nomenclatura")
        opportunity.object_type = _first_text(row, "objeto", "Objeto de Contratacion", "Objeto de Contratación")
        opportunity.description = _first_text(row, "descripcion", "Descripcion de Objeto", "Descripción de Objeto")
        catalog_entity = find_entity(opportunity.entity)
        opportunity.region = _first_text(row, "region", "Departamento", "Región") or (catalog_entity or {}).get("region", "")
        opportunity.buyer_ruc = _first_text(row, "ruc", "RUC") or (catalog_entity or {}).get("ruc", "")
        opportunity.ocid = _as_text(row.get("ocid"))
        opportunity.tender_id = _as_text(row.get("tender_id"))
        opportunity.ocds_source_id = _as_text(row.get("source_id"))
        opportunity.release_id = _as_text(row.get("release_id"))
        documents_payload = _as_text(row.get("documentos_ocds"))
        if documents_payload:
            try:
                parsed_documents = json.loads(documents_payload)
                opportunity.documents_count = len(parsed_documents) if isinstance(parsed_documents, list) else 0
            except json.JSONDecodeError:
                opportunity.documents_count = 0
        else:
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
        opportunity.currency = _first_text(row, "moneda", "Moneda")
        opportunity.status = _first_text(row, "estado_operativo", "estado_comercial", "Estado Comercial")
        opportunity.priority = _first_text(row, "prioridad") or "C"
        opportunity.score = int(_as_float(row.get("score")))
        opportunity.reasons = _as_text(row.get("motivos_score"))
        opportunity.detail_url = _first_text(row, "url_detalle", "detalle_url")
        opportunity.requirement_pdf_url = _as_text(row.get("requerimiento_pdf"))
        opportunity.requirement_pdf_local = _as_text(row.get("requerimiento_pdf_local"))
        opportunity.publication_date = _merge_datetime(
            opportunity.publication_date,
            row.get("fecha_publicacion") or row.get("Fecha y Hora de Publicacion") or row.get("Fecha y Hora de Publicación"),
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
