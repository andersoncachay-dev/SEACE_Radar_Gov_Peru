from __future__ import annotations

import traceback
import re
from datetime import datetime, timedelta
from threading import Event, Lock
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.keyword_matching import contains_complete_phrase

from ..config import settings
from ..database import SessionLocal
from ..models import Opportunity, ScrapeRun, SearchProfile
from .ingestion_service import upsert_opportunities
from .notification_service import evaluate_alerts, evaluate_new_opportunity_alerts, send_pending_alerts


_mercado_publico_run_lock = Lock()
_run_cancel_events: dict[int, Event] = {}
_run_cancel_events_lock = Lock()


class RunCancelled(Exception):
    pass


def _cancel_event(run_id: int) -> Event:
    with _run_cancel_events_lock:
        return _run_cancel_events.setdefault(run_id, Event())


def request_run_cancel(run_id: int) -> None:
    _cancel_event(run_id).set()


def _forget_cancel_event(run_id: int) -> None:
    with _run_cancel_events_lock:
        _run_cancel_events.pop(run_id, None)


def reconcile_interrupted_runs() -> int:
    """Close in-flight runs whose background task was lost during a service restart."""
    db: Session = SessionLocal()
    try:
        interrupted = list(
            db.scalars(
                select(ScrapeRun).where(ScrapeRun.status.in_(("queued", "running")))
            ).all()
        )
        finished_at = datetime.utcnow()
        for run in interrupted:
            run.finished_at = finished_at
            if run.cancel_requested:
                run.status = "cancelled"
                run.progress_message = "Búsqueda detenida"
                run.error_message = ""
            else:
                run.status = "failed"
                run.progress_message = "Búsqueda interrumpida por reinicio del servicio"
                run.error_message = "La ejecución en segundo plano se interrumpió antes de finalizar. Puedes iniciar una nueva búsqueda."
        db.commit()
        return len(interrupted)
    finally:
        db.close()


def _period_values(payload: dict, plural_key: str, singular_key: str) -> set[int]:
    raw_values = payload.get(plural_key) or payload.get(singular_key) or []
    if isinstance(raw_values, str):
        raw_values = raw_values.split(",")
    values: set[int] = set()
    for item in raw_values:
        try:
            text = str(item).strip()
            if text:
                values.add(int(text))
        except Exception:
            continue
    return values


def _filter_dataframe_period(rows: Any, payload: dict):
    if rows is None or getattr(rows, "empty", True):
        return rows
    years = _period_values(payload, "years", "year")
    months = _period_values(payload, "months", "month")
    if not years and not months and not payload.get("publication_date_from") and not payload.get("publication_date_to"):
        return rows
    publication_column = "fecha_publicacion" if "fecha_publicacion" in rows.columns else "Fecha y Hora de Publicacion"
    proposal_column = "propuesta_fin" if "propuesta_fin" in rows.columns else None
    is_chile = str(payload.get("source") or "").lower().startswith("mercado_publico")
    if publication_column not in rows.columns and proposal_column is None:
        return rows
    publication_dates = rows[publication_column] if publication_column in rows.columns else None
    proposal_dates = rows[proposal_column] if proposal_column else None
    # Mercado Publico presents searches by their closing date. For Chile, a
    # selected month therefore means the complete month of proposal closing,
    # including future months, even when the tender was published earlier.
    if is_chile and proposal_dates is not None:
        dates = proposal_dates if publication_dates is None else proposal_dates.combine_first(publication_dates)
    elif publication_dates is not None:
        dates = publication_dates if proposal_dates is None else publication_dates.combine_first(proposal_dates)
    else:
        dates = proposal_dates
    mask = True
    if years:
        mask = dates.dt.year.isin(years)
    if months:
        month_mask = dates.dt.month.isin(months)
        mask = month_mask if mask is True else mask & month_mask
    publication_from = payload.get("publication_date_from")
    publication_to = payload.get("publication_date_to")
    if publication_from:
        from_mask = dates.dt.normalize() >= datetime.strptime(publication_from, "%Y-%m-%d")
        mask = from_mask if mask is True else mask & from_mask
    if publication_to:
        to_mask = dates.dt.normalize() <= datetime.strptime(publication_to, "%Y-%m-%d")
        mask = to_mask if mask is True else mask & to_mask
    if "force_revalidation" in rows.columns:
        # A saved row may reveal a corrected deadline outside the selected
        # month after its sheet is opened. Keep it so the correction reaches
        # the database instead of preserving the stale date forever.
        mask = mask | rows["force_revalidation"].fillna(False).astype(bool)
    return rows[mask].copy()


def _terminal_status(value: Any) -> bool:
    normalized = str(value or "").strip().casefold()
    return any(term in normalized for term in ("cerrad", "culminad", "adjudicad", "desiert", "revocad", "seleccionad"))


def _active_row_mask(rows: Any):
    status_columns = [column for column in ("estado_comercial", "vigencia") if column in rows.columns]
    terminal_mask = False
    for column in status_columns:
        column_mask = rows[column].fillna("").map(_terminal_status)
        terminal_mask = column_mask if terminal_mask is False else terminal_mask | column_mask
    active_mask = ~terminal_mask if terminal_mask is not False else rows.index.to_series().map(lambda _: True)
    if "propuesta_fin" in rows.columns:
        deadlines = rows["propuesta_fin"]
        deadline_mask = deadlines.isna() | (deadlines > datetime.now())
        active_mask = active_mask & deadline_mask
    return active_mask


def _existing_active_nomenclatures(db: Session, source: str) -> set[str]:
    now = datetime.utcnow()
    items = db.scalars(
        select(Opportunity).where(
            Opportunity.source == source,
            Opportunity.is_archived.is_(False),
        )
    ).all()
    return {
        str(item.nomenclature or item.external_id).strip().casefold()
        for item in items
        if not _terminal_status(item.status)
        and (item.proposal_deadline is None or item.proposal_deadline > now)
        and str(item.nomenclature or item.external_id).strip()
    }


def _finalize_expired_opportunities(db: Session, source: str) -> int:
    now = datetime.utcnow()
    items = db.scalars(
        select(Opportunity).where(
            Opportunity.source == source,
            Opportunity.is_archived.is_(False),
            Opportunity.proposal_deadline.is_not(None),
            Opportunity.proposal_deadline <= now,
        )
    ).all()
    changed = 0
    for item in items:
        if not _terminal_status(item.status):
            item.status = "Proceso Culminado"
            changed += 1
    if changed:
        db.commit()
    return changed


def _finalize_stale_peru_consultations(db: Session, source: str, days: int = 30) -> int:
    """Close Peru candidates whose enquiry window expired over ``days`` ago.

    A future proposal deadline already validated in SEACE takes precedence. A
    closed row remains available for explicit manual revalidation from the UI.
    """
    now = datetime.utcnow()
    cutoff = now - timedelta(days=days)
    items = db.scalars(
        select(Opportunity).where(
            Opportunity.source == source,
            Opportunity.is_archived.is_(False),
            Opportunity.consultation_deadline.is_not(None),
            Opportunity.consultation_deadline < cutoff,
        )
    ).all()
    changed = 0
    for item in items:
        if item.proposal_deadline is not None and item.proposal_deadline > now:
            continue
        if not _terminal_status(item.status):
            item.status = "Proceso Culminado"
            changed += 1
    if changed:
        db.commit()
    return changed


def _filter_incremental_rows(rows: Any, payload: dict, existing_active: set[str], diagnostics: list[str]):
    if rows is None or getattr(rows, "empty", True):
        return rows
    if not payload.get("automatic_incremental"):
        return _filter_dataframe_period(rows, payload)
    if "automatic_discovery" in rows.columns:
        discovery = rows[rows["automatic_discovery"].fillna(False).astype(bool)].copy()
    else:
        discovery = _filter_dataframe_period(rows, payload)
    if discovery is not None and not discovery.empty:
        discovery = discovery[_active_row_mask(discovery)].copy()
    nomenclature_column = "nomenclatura" if "nomenclatura" in rows.columns else "Nomenclatura"
    if nomenclature_column in rows.columns and existing_active:
        existing_mask = rows[nomenclature_column].fillna("").astype(str).str.strip().str.casefold().isin(existing_active)
        revalidated = rows[existing_mask].copy()
    else:
        revalidated = rows.iloc[0:0].copy()
    combined = rows.loc[discovery.index.union(revalidated.index)].copy()
    diagnostics.append(
        f"Incremental: {len(discovery)} nuevos/vigentes en ventana + "
        f"{len(revalidated)} vigentes existentes revalidados; {len(combined)} filas unicas"
    )
    return combined


def _filter_dataframe_keyword(rows: Any, keyword: str):
    if rows is None or getattr(rows, "empty", True) or not str(keyword or "").strip():
        return rows
    searchable_columns = [
        column for column in ("entidad", "nomenclatura", "objeto", "descripcion")
        if column in rows.columns
    ]
    if not searchable_columns:
        return rows.iloc[0:0].copy()
    mask = rows.apply(
        lambda row: contains_complete_phrase(
            " ".join(str(row.get(column, "") or "") for column in searchable_columns),
            keyword,
        ),
        axis=1,
    )
    return rows[mask].copy()


def _filter_dataframe_entity(rows: Any, entity_filter: str | None):
    if rows is None or getattr(rows, "empty", True) or not str(entity_filter or "").strip():
        return rows
    entity_column = "entidad" if "entidad" in rows.columns else "Entidad" if "Entidad" in rows.columns else None
    if entity_column is None:
        return rows.iloc[0:0].copy()
    normalized_entity = str(entity_filter).strip().casefold()
    mask = rows[entity_column].fillna("").astype(str).str.strip().str.casefold().eq(normalized_entity)
    return rows[mask].copy()


def _filter_dataframe_nomenclature(rows: Any, nomenclature: str | None):
    if rows is None or getattr(rows, "empty", True) or not str(nomenclature or "").strip():
        return rows
    nomenclature_column = "nomenclatura" if "nomenclatura" in rows.columns else "Nomenclatura" if "Nomenclatura" in rows.columns else None
    if nomenclature_column is None:
        return rows.iloc[0:0].copy()
    normalized_nomenclature = str(nomenclature).strip().casefold()
    mask = rows[nomenclature_column].fillna("").astype(str).str.strip().str.casefold().eq(normalized_nomenclature)
    return rows[mask].copy()


def _int_list(payload: dict, plural_key: str, single_key: str, default: int | None = None) -> list[int]:
    raw = payload.get(plural_key)
    if raw is None:
        raw = payload.get(single_key)
    if raw is None or raw == "":
        return [default] if default is not None else []
    values = raw if isinstance(raw, list) else str(raw).split(",")
    parsed: list[int] = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        parsed.append(int(text))
    return parsed or ([default] if default is not None else [])


def _schedule_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _year_for_nomenclature(nomenclature: str, default: str) -> str:
    """SEACE's search requires a specific "Año de la Convocatoria".

    Most nomenclatures embed their own convocation year (e.g.
    ``CP-ABR-5-2026-MDL/DEC-1``); prefer that over the run's overall
    ``details_year`` so a target from a different year still resolves.
    """
    match = re.search(r"-(20\d{2})-", str(nomenclature or ""))
    return match.group(1) if match else default


def _recent_consultation_mask(raw: Any, days: int = 30) -> list[bool]:
    if raw is None or getattr(raw, "empty", True) or "consulta_fin" not in raw.columns:
        return []
    now = datetime.utcnow()
    cutoff = now - timedelta(days=days)
    ceiling = now + timedelta(days=days)
    mask: list[bool] = []
    for value in raw["consulta_fin"]:
        parsed = None
        try:
            parsed = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
        except Exception:
            parsed = None
        if parsed is None:
            try:
                import pandas as pd

                parsed_value = pd.to_datetime(value, errors="coerce", dayfirst=True)
                parsed = None if pd.isna(parsed_value) else parsed_value.to_pydatetime()
            except Exception:
                parsed = None
        mask.append(isinstance(parsed, datetime) and cutoff <= parsed <= ceiling)
    return mask


def _recent_consultation_rows(raw: Any, days: int = 30) -> int:
    return sum(_recent_consultation_mask(raw, days))


def _peru_schedule_targets(
    db: Session, source: str, raw: Any, *, allow_older: bool = False, only_new: bool = False
) -> list[str]:
    """Mark Peru rows that still need an authoritative SEACE schedule.

    OCDS discovers the process and its publication date. A proposal deadline is
    only considered validated after SEACE supplied it, so missing proposal dates
    form a progressive queue across automatic runs.

    ``only_new`` restricts eligibility to nomenclatures that are not yet saved
    at all - used by automatic scheduled runs so they spend time/proxy budget
    on genuinely new processes instead of re-searching SEACE for ones already
    in the opportunities table (whether validated or still pending). Manual
    revalidation (the per-row "Revalidar" action) does not set this flag, so it
    can still target an already-saved, still-pending row on demand.
    """
    if raw is None or getattr(raw, "empty", True) or "Nomenclatura" not in raw.columns:
        return []
    nomenclatures = [str(value).strip() for value in raw["Nomenclatura"].dropna() if str(value).strip()]
    if not nomenclatures:
        return []
    existing = db.scalars(
        select(Opportunity).where(
            Opportunity.source == source,
            Opportunity.external_id.in_(nomenclatures),
        )
    ).all()
    if only_new:
        validated = {
            str(item.external_id or item.nomenclature).strip().casefold() for item in existing
        }
    else:
        validated = {
            str(item.external_id or item.nomenclature).strip().casefold()
            for item in existing
            if item.schedule_source == "seace" and item.schedule_validated_at is not None
        }
    consultation_column = "consulta_fin"
    cutoff = datetime.utcnow() - timedelta(days=30)
    ceiling = datetime.utcnow() + timedelta(days=30)
    eligible: set[str] = set()
    for _, row in raw.iterrows():
        nomenclature = str(row.get("Nomenclatura") or "").strip()
        if not nomenclature or nomenclature.casefold() in validated:
            continue
        if allow_older:
            eligible.add(nomenclature.casefold())
            continue
        consultation_date = row.get(consultation_column)
        try:
            import pandas as pd
            from src.normalizer import _parse_datetime_value

            parsed = _parse_datetime_value(consultation_date)
            consultation = None if pd.isna(parsed) else parsed.to_pydatetime()
        except Exception:
            consultation = None
        if consultation is not None and cutoff <= consultation <= ceiling:
            eligible.add(nomenclature.casefold())
    target_keys = eligible
    raw["replace_schedule"] = raw["Nomenclatura"].fillna("").astype(str).str.strip().str.casefold().isin(target_keys)
    return [nomenclature for nomenclature in nomenclatures if nomenclature.casefold() in target_keys]


def _peru_pending_schedule_rows(
    db: Session,
    source: str,
    keyword: str,
    limit: int,
    *,
    allow_older: bool = False,
) -> list[dict[str, Any]]:
    """Return saved Peru rows whose schedule has not been proven by SEACE.

    This queue is independent from the current OCDS response. Consequently a
    temporary empty OCDS window cannot prevent correction of stored deadlines.
    """
    candidates = db.scalars(
        select(Opportunity).where(
            Opportunity.source == source,
            Opportunity.is_archived.is_(False),
        ).order_by(Opportunity.updated_at.asc())
    ).all()
    rows: list[dict[str, Any]] = []
    now = datetime.utcnow()
    cutoff = now - timedelta(days=30)
    ceiling = now + timedelta(days=30)
    for item in candidates:
        if item.schedule_source == "seace" and item.schedule_validated_at is not None:
            continue
        searchable = " ".join((item.entity or "", item.nomenclature or "", item.description or ""))
        if keyword and not contains_complete_phrase(searchable, keyword):
            continue
        if item.consultation_deadline is None:
            continue
        if not allow_older and not (cutoff <= item.consultation_deadline <= ceiling):
            continue
        rows.append(
            {
                "Nomenclatura": item.nomenclature or item.external_id,
                "Nombre o Sigla de la Entidad": item.entity,
                "Descripcion de Objeto": item.description,
                "Fecha y Hora de Publicacion": item.publication_date,
                "consulta_fin": item.consultation_deadline,
                "propuesta_fin": None,
                "Estado Comercial": item.status,
                "Vigencia": item.status,
                "url_detalle": item.detail_url,
                "Moneda": item.currency or "PEN",
                "region": item.region or "Peru",
                "replace_schedule": True,
                "force_revalidation": True,
            }
        )
        if len(rows) >= max(1, limit):
            break
    return rows


def _merge_seace_schedule(raw, seace_raw, diagnostics: list[str]):
    if raw is None or raw.empty or seace_raw is None or seace_raw.empty:
        return raw
    schedule_columns = [
        "consulta_inicio",
        "consulta_fin",
        "propuesta_inicio",
        "propuesta_fin",
        "convocatoria_inicio",
        "convocatoria_fin",
        "registro_inicio",
        "registro_fin",
        "absolucion_inicio",
        "absolucion_fin",
        "integracion_inicio",
        "integracion_fin",
        "evaluacion_inicio",
        "evaluacion_fin",
        "buena_pro_inicio",
        "buena_pro_fin",
        "Estado Comercial",
        "Vigencia",
    ]
    by_nomenclature = {
        _schedule_key(row.get("Nomenclatura", "")): row
        for _, row in seace_raw.iterrows()
        if _schedule_key(row.get("Nomenclatura", ""))
    }
    applied = 0
    merged = raw.copy()
    for column in schedule_columns:
        if column in merged.columns:
            merged[column] = merged[column].astype("object")
    for idx, row in merged.iterrows():
        key = _schedule_key(row.get("Nomenclatura", ""))
        seace_row = by_nomenclature.get(key)
        if seace_row is None:
            seace_row = next(
                (
                    candidate
                    for candidate_key, candidate in by_nomenclature.items()
                    if key and candidate_key and (key in candidate_key or candidate_key in key)
                ),
                None,
            )
            if seace_row is None:
                continue
        touched = False
        for column in schedule_columns:
            value = seace_row.get(column)
            if value is not None and str(value).strip():
                merged.at[idx, column] = value
                touched = True
        if touched:
            # This marker is the authoritative distinction between an OCDS
            # discovery date and a schedule actually read from SEACE/SV3.
            merged.at[idx, "schedule_source"] = "seace"
            merged.at[idx, "schedule_validated_at"] = datetime.utcnow()
            applied += 1
    diagnostics.append(f"OCDS cronograma SEACE aplicado por nomenclatura: {applied}/{len(merged)}")
    return merged


def _seace_has_proposal_schedule(seace_raw, nomenclature: str) -> bool:
    """Confirm that SEACE returned the requested process with Fin Propuesta.

    A SEACE search can return a non-empty results table even when the exact
    process was not enriched. Treating that table as success prevents the
    keyword fallback and leaves the saved opportunity without its deadline.
    """
    if seace_raw is None or seace_raw.empty:
        return False
    requested_key = _schedule_key(nomenclature)
    if not requested_key or "Nomenclatura" not in seace_raw.columns:
        return False
    for _, row in seace_raw.iterrows():
        candidate_key = _schedule_key(row.get("Nomenclatura", ""))
        if candidate_key != requested_key:
            continue
        proposal_end = row.get("propuesta_fin")
        normalized_end = str(proposal_end).strip().casefold() if proposal_end is not None else ""
        if normalized_end and normalized_end not in {"nan", "nat", "none"}:
            return True
    return False


def _persist_peru_opportunities(
    db: Session, raw, payload: dict, ocds_keyword: str, max_results: int, source: str, run_id: int
) -> int:
    """Normalize, score and upsert the current Peru dataframe.

    Called twice per run: once right after OCDS discovery (before SEACE
    enrichment, which is slower and more failure-prone - a proxy hiccup or
    container restart there must not cost the OCDS discoveries themselves),
    and again at the end once SEACE has filled in what proposal deadlines it
    could. upsert_opportunities matches by nomenclature, so the second call
    updates the same rows in place rather than duplicating them.
    """
    from src.normalizer import normalize_columns
    from src.scoring import enriquecer_oportunidades
    from .scoring_config_service import get_scoring_config

    normalized = normalize_columns(raw) if raw is not None and not raw.empty else raw
    normalized = _filter_dataframe_entity(normalized, payload.get("entity_filter"))
    normalized = _filter_dataframe_nomenclature(normalized, payload.get("nomenclature"))
    normalized = _filter_dataframe_keyword(normalized, ocds_keyword)
    enriched = (
        enriquecer_oportunidades(normalized, get_scoring_config(db, "peru"))
        if normalized is not None and not normalized.empty
        else normalized
    )
    if enriched is not None and not enriched.empty and max_results:
        enriched = enriched.head(max_results).copy()
    return upsert_opportunities(db, enriched, source, run_id=run_id)


_LIMA_TZ = ZoneInfo("America/Lima")


def _month_add(year: int, month: int, delta: int) -> tuple[int, int]:
    index = (year * 12 + (month - 1)) + delta
    return index // 12, index % 12 + 1


def chile_closing_window(payload: dict, now: datetime | None = None) -> tuple[str, str]:
    """Fecha de Cierre range for a Chile search: day 1 of the earliest
    selected month/year through the last day of the month *after* the latest
    selected month/year (or, with nothing selected, current month + next
    month). Mercado Publico's Excel export always reports Fecha Cierre no
    matter which date-type filter was applied in the form, so every Chile
    search - manual or automatic - is anchored to that field.
    """
    import calendar

    years = sorted(_period_values(payload, "years", "year"))
    months = sorted(_period_values(payload, "months", "month"))
    current = now or datetime.now(_LIMA_TZ)
    start_year = years[0] if years else current.year
    start_month = months[0] if months else current.month
    end_year = years[-1] if years else current.year
    end_month = months[-1] if months else current.month
    end_year, end_month = _month_add(end_year, end_month, 1)
    end_day = calendar.monthrange(end_year, end_month)[1]
    return f"{start_year:04d}-{start_month:02d}-01", f"{end_year:04d}-{end_month:02d}-{end_day:02d}"


def _chile_rows_needing_detail(db: Session, source: str, rows: list[dict]) -> list[str]:
    """Which Nomenclaturas from a fresh Excel snapshot should get a ficha visit.

    Rule: Estado = Publicada, OR the row already existed and its Estado or
    Fecha Cierre changed since our last snapshot. A brand-new row whose Estado
    is already terminal (Cerrada/Adjudicada/Desierta/Revocada) is stored from
    the Excel data alone and never spends a browser visit on its ficha.
    """
    import pandas as pd

    nomenclatures = [str(row.get("Nomenclatura", "")).strip() for row in rows if str(row.get("Nomenclatura", "")).strip()]
    if not nomenclatures:
        return []
    existing = db.scalars(
        select(Opportunity).where(Opportunity.source == source, Opportunity.external_id.in_(nomenclatures))
    ).all()
    existing_by_key = {item.external_id.strip().casefold(): item for item in existing}
    targets: list[str] = []
    for row in rows:
        nomenclature = str(row.get("Nomenclatura", "")).strip()
        if not nomenclature:
            continue
        estado_ml = str(row.get("estado_mercado_publico", "")).strip().casefold()
        if estado_ml == "publicada":
            targets.append(nomenclature)
            continue
        current = existing_by_key.get(nomenclature.casefold())
        if current is None:
            continue
        status_changed = (current.source_status or "").strip().casefold() != estado_ml
        closing_changed = False
        incoming_closing = pd.to_datetime(row.get("propuesta_fin"), dayfirst=True, errors="coerce")
        if not pd.isna(incoming_closing):
            if current.proposal_deadline is None:
                closing_changed = True
            else:
                closing_changed = abs((incoming_closing.to_pydatetime() - current.proposal_deadline).total_seconds()) > 60
        if status_changed or closing_changed:
            targets.append(nomenclature)
    return targets


def _drop_archived_chile_rows(db: Session, rows: list[dict], diagnostics: list[str]) -> list[dict]:
    """Discard rows the user already sent to Historico de procesos eliminados.

    A discard is a persistent business decision, not a data gap: if the
    process still shows up in a fresh Excel snapshot (still Publicada, or its
    Estado/Fecha Cierre moved), it must not come back as an "update" and must
    never trigger an alert. ``upsert_opportunities`` already refuses to touch
    an archived opportunity, but filtering here also skips the wasted ficha
    visit for it.
    """
    keys = {
        str(row.get("Nomenclatura", "")).strip().casefold()
        for row in rows
        if str(row.get("Nomenclatura", "")).strip()
    }
    if not keys:
        return rows
    archived_keys = set(
        db.scalars(
            select(Opportunity.archive_key).where(
                Opportunity.is_archived.is_(True),
                Opportunity.archive_country == "chile",
                Opportunity.archive_key.in_(keys),
            )
        ).all()
    )
    if not archived_keys:
        return rows
    filtered = [
        row for row in rows
        if str(row.get("Nomenclatura", "")).strip().casefold() not in archived_keys
    ]
    diagnostics.append(
        f"Mercado Publico licitaciones: {len(rows) - len(filtered)} procesos omitidos "
        "(ya estan en el historico de procesos eliminados)"
    )
    return filtered


def _merge_mercado_publico_chile_details(rows: list[dict], detail_rows: list[dict], diagnostics: list[str]) -> list[dict]:
    by_key = {str(row.get("Nomenclatura", "")).strip().casefold(): row for row in detail_rows if row.get("Nomenclatura")}
    applied = 0
    for row in rows:
        key = str(row.get("Nomenclatura", "")).strip().casefold()
        detail = by_key.get(key)
        if not detail:
            continue
        for field in (
            "Fecha y Hora de Publicacion",
            "convocatoria_inicio",
            "consulta_fin",
            "propuesta_fin",
            "buena_pro_fin",
            "contract_duration",
            "region",
            "url_detalle",
        ):
            value = detail.get(field)
            if value:
                row[field] = value
        applied += 1
    diagnostics.append(f"Mercado Publico licitaciones: fichas aplicadas a {applied}/{len(detail_rows)} procesos")
    return rows


def execute_scrape_run(run_id: int, payload: dict) -> None:
    db: Session = SessionLocal()
    run = db.get(ScrapeRun, run_id)
    if not run:
        db.close()
        return

    mercado_publico_lock_acquired = False
    cancel_event = _cancel_event(run_id)

    def check_cancelled() -> None:
        if cancel_event.is_set() or bool(run.cancel_requested) or run.status == "cancelled":
            raise RunCancelled("Búsqueda detenida por el usuario")

    def update_progress(value: float, message: str) -> None:
        check_cancelled()
        run.progress = max(int(run.progress or 0), min(99, round(value)))
        run.progress_message = message[:255]
        db.commit()

    try:
        check_cancelled()
        profile = db.get(SearchProfile, payload.get("search_profile_id")) if payload.get("search_profile_id") else None
        source = profile.source if profile else payload.get("source", "seace_public_browser")
        keyword = profile.keyword if profile else payload.get("keyword", "satelital")
        year = profile.year if profile else payload.get("year", "2026")
        version = profile.version if profile else payload.get("version", "Seace 3")
        month = payload.get("month")
        max_results = profile.max_results if profile else int(payload.get("max_results", 25))
        max_details = int(payload.get("max_details", min(max_results, 15)) or 0)
        period_text = ""
        if payload.get("year") or payload.get("month") or payload.get("years") or payload.get("months"):
            period_text = f" | anos={payload.get('years') or payload.get('year') or '-'} | meses={payload.get('months') or payload.get('month') or '-'}"
        if payload.get("publication_date_from") or payload.get("publication_date_to"):
            date_label = "cierres" if payload.get("date_filter_type") == "closing" else "publicados"
            period_text += (
                f" | {date_label}={payload.get('publication_date_from') or '-'}.."
                f"{payload.get('publication_date_to') or '-'}"
            )
        if payload.get("active_only"):
            period_text += " | solo_vigentes=True"
        commercial_mode = "all" if str(payload.get("commercial_mode", "active")).lower() == "all" else "active"
        config_line = (
            f"Configuracion: keyword={keyword} | max_resultados={max_results} | "
            f"leer_detalles={bool(payload.get('enrich_details', False))} | max_detalles={max_details} | "
            f"semaforo={commercial_mode}{period_text}"
        )

        if str(source).startswith("mercado_publico"):
            run.diagnostics = f"{config_line}\nEn cola: esperando turno para consultar Mercado Publico."
            run.progress = 0
            run.progress_message = "En cola para consultar Mercado Público"
            db.commit()
            while not mercado_publico_lock_acquired:
                check_cancelled()
                mercado_publico_lock_acquired = _mercado_publico_run_lock.acquire(timeout=0.5)

        run.status = "running"
        run.started_at = datetime.utcnow()
        run.progress = 2
        run.progress_message = "Preparando búsqueda"
        run.diagnostics = config_line
        db.commit()

        if source == "menor8_browser" and not settings.enable_menor8_module:
            raise RuntimeError("Menores a 8 UIT esta deshabilitado temporalmente hasta estabilizar el modulo.")

        if source == "seace_public_browser":
            from src.normalizer import normalize_columns
            from src.scoring import enriquecer_oportunidades
            from src.seace_browser_scraper import search_seace_public_browser

            raw, diagnostics = search_seace_public_browser(
                keyword=keyword,
                year=year,
                version=version,
                headless=True,
                enrich_details=bool(payload.get("enrich_details", False)),
                max_details=max_details,
                progress_callback=lambda value, message: update_progress(5 + value * 75, message),
                cancel_callback=check_cancelled,
            )
            update_progress(82, "Procesando resultados de SEACE")
            normalized = normalize_columns(raw) if raw is not None and not raw.empty else raw
            normalized = _filter_dataframe_entity(normalized, payload.get("entity_filter"))
            normalized = _filter_dataframe_nomenclature(normalized, payload.get("nomenclature"))
            normalized = _filter_dataframe_keyword(normalized, keyword)
            from .scoring_config_service import get_scoring_config
            enriched = enriquecer_oportunidades(normalized, get_scoring_config(db, "peru")) if normalized is not None and not normalized.empty else normalized
            if enriched is not None and not enriched.empty and max_results:
                enriched = enriched.head(max_results).copy()
            rows_found = upsert_opportunities(db, enriched, source, run_id=run.id)
        elif (
            source == "mercado_publico_lmp_gc"
            and not payload.get("automatic_incremental")
            and payload.get("direct_detail_lookup")
            and str(payload.get("nomenclature") or "").strip()
        ):
            # "Buscar Fecha en Mercado Publico CL" button: revalidate one known
            # process directly by its code. No listing/date-range search is
            # needed - Mercado Publico's search-by-code returns exactly that
            # process, so we go straight to its ficha (Etapas y plazos +
            # duracion de contrato) and refresh whichever dates it has. The
            # ficha alone has no entity/description, so this must only touch
            # an opportunity already saved from a prior discovery (upsert
            # preserves its existing fields); a brand-new nomenclature lookup
            # still goes through the branch below.
            from src.mercado_publico_scraper import search_mercado_publico_details_by_code
            from src.normalizer import normalize_columns
            import pandas as pd

            persisted_source = "mercado_publico_browser"
            requested_nomenclature = str(payload.get("nomenclature")).strip()
            update_progress(10, f"Buscando ficha de {requested_nomenclature} en Mercado Público")
            detail_rows, diagnostics = search_mercado_publico_details_by_code(
                [requested_nomenclature],
                headless=True,
                progress_callback=lambda value, message: update_progress(10 + value * 75, message),
                cancel_callback=check_cancelled,
            )
            if not detail_rows:
                raise RuntimeError(f"No se encontro la ficha de {requested_nomenclature} en Mercado Publico.")
            update_progress(90, "Guardando fechas revalidadas")
            raw = pd.DataFrame(detail_rows)
            normalized = normalize_columns(raw)
            rows_found = upsert_opportunities(db, normalized, persisted_source, run_id=run.id)
        elif source == "mercado_publico_lmp_gc":
            # Chile licitaciones: bulk Excel discovery (Fecha de Cierre) +
            # selective ficha enrichment. Shared by manual UI searches and the
            # automatic scheduler (automatic_incremental=True) alike - both
            # need the same "mes actual + mes siguiente" window and the same
            # rule for when a ficha visit is worth spending.
            from src.mercado_publico_scraper import (
                search_mercado_publico_bulk_excel,
                search_mercado_publico_details_by_code,
            )
            from src.normalizer import normalize_columns
            from src.scoring import enriquecer_oportunidades
            from .scoring_config_service import get_scoring_config
            import pandas as pd

            persisted_source = "mercado_publico_browser"
            date_from, date_to = chile_closing_window(payload)
            expired_count = _finalize_expired_opportunities(db, persisted_source)
            diagnostics: list[str] = []
            if expired_count:
                diagnostics.append(f"Mercado Publico licitaciones: {expired_count} procesos vencidos cerrados localmente")
            if settings.enable_chile_grandes_compras:
                diagnostics.append(
                    "Mercado Publico grandes_compras: aun no soportado por este flujo; se consultaron solo licitaciones."
                )
            update_progress(5, f"Buscando Mercado Publico (cierre {date_from} a {date_to})")
            bulk_rows, bulk_diagnostics = search_mercado_publico_bulk_excel(
                keyword=keyword,
                date_from=date_from,
                date_to=date_to,
                headless=True,
                progress_callback=lambda value, message: update_progress(5 + value * 40, message),
                cancel_callback=check_cancelled,
            )
            diagnostics.extend(bulk_diagnostics)
            bulk_rows = _drop_archived_chile_rows(db, bulk_rows, diagnostics)
            update_progress(45, f"{len(bulk_rows)} procesos encontrados; comparando con la base")

            detail_targets = _chile_rows_needing_detail(db, persisted_source, bulk_rows)
            diagnostics.append(
                f"Mercado Publico licitaciones: {len(detail_targets)}/{len(bulk_rows)} procesos requieren ficha "
                "(Publicada o con cambio de estado/fecha de cierre)"
            )
            if detail_targets:
                detail_rows, detail_diagnostics = search_mercado_publico_details_by_code(
                    detail_targets,
                    headless=True,
                    progress_callback=lambda value, message: update_progress(50 + value * 35, message),
                    cancel_callback=check_cancelled,
                )
                diagnostics.extend(detail_diagnostics)
                bulk_rows = _merge_mercado_publico_chile_details(bulk_rows, detail_rows, diagnostics)

            update_progress(88, "Procesando resultados de Mercado Público")
            raw = pd.DataFrame(bulk_rows) if bulk_rows else pd.DataFrame()
            normalized = normalize_columns(raw) if not raw.empty else raw
            normalized = _filter_dataframe_entity(normalized, payload.get("entity_filter"))
            normalized = _filter_dataframe_nomenclature(normalized, payload.get("nomenclature"))
            normalized = _filter_dataframe_keyword(normalized, keyword)
            enriched = enriquecer_oportunidades(normalized, get_scoring_config(db, "chile")) if normalized is not None and not normalized.empty else normalized
            if enriched is not None and not enriched.empty and max_results:
                enriched = enriched.head(max_results).copy()
            rows_found = upsert_opportunities(db, enriched, persisted_source, run_id=run.id)
        elif source == "mercado_publico_grandes_compras":
            from src.mercado_publico_scraper import search_mercado_publico
            from src.normalizer import normalize_columns
            from src.scoring import enriquecer_oportunidades

            mode = "grandes_compras"
            raw, diagnostics = search_mercado_publico(
                keyword=keyword,
                mode=mode,
                headless=True,
                max_results=max_results,
                enrich_details=bool(payload.get("enrich_details", False)),
                enrich_closed_details=bool(payload.get("revalidate_closed_detail", False)),
                include_detail_attachments=False,
                publication_date_from=payload.get("publication_date_from"),
                publication_date_to=payload.get("publication_date_to"),
                date_filter_type=payload.get("date_filter_type", "publication"),
                include_active_revalidation=bool(payload.get("automatic_incremental")) and mode == "licitaciones",
                max_details=max_details,
                years=sorted(_period_values(payload, "years", "year")),
                months=sorted(_period_values(payload, "months", "month")),
                progress_callback=lambda value, message: update_progress(5 + value * 75, message),
                cancel_callback=check_cancelled,
            )
            update_progress(82, "Procesando resultados de Mercado Público")
            normalized = normalize_columns(raw) if raw is not None and not raw.empty else raw
            normalized = _filter_dataframe_entity(normalized, payload.get("entity_filter"))
            normalized = _filter_dataframe_nomenclature(normalized, payload.get("nomenclature"))
            if source.startswith("mercado_publico"):
                existing_active = _existing_active_nomenclatures(db, source)
                expired_count = _finalize_expired_opportunities(db, source)
                if expired_count:
                    diagnostics.append(f"Mercado Publico {mode}: {expired_count} procesos vencidos cerrados localmente")
                normalized = _filter_incremental_rows(normalized, payload, existing_active, diagnostics)
            normalized = _filter_dataframe_keyword(normalized, keyword)
            from .scoring_config_service import get_scoring_config
            enriched = enriquecer_oportunidades(normalized, get_scoring_config(db, "chile")) if normalized is not None and not normalized.empty else normalized
            if enriched is not None and not enriched.empty and max_results:
                enriched = enriched.head(max_results).copy()
            rows_found = upsert_opportunities(db, enriched, source, run_id=run.id)
        elif source == "oece_ocds_api":
            from src.oece_ocds_connector import search_oece_ocds

            selected_years = _int_list(payload, "years", "year", datetime.utcnow().year)
            selected_months = _int_list(payload, "months", "month", None)
            ocds_keyword = payload.get("nomenclature") or keyword
            raw, diagnostics = search_oece_ocds(
                keyword=ocds_keyword,
                year=selected_years[0] if selected_years else int(year or datetime.utcnow().year),
                month=selected_months[0] if len(selected_months) == 1 else None,
                years=selected_years,
                months=selected_months or None,
                max_results=max_results,
                max_pages=max(3, min(8, max_results)),
                page_size=100,
                allow_release_fallback=False,
                progress_callback=lambda value, message: update_progress(5 + value * 45, message),
                cancel_callback=check_cancelled,
            )
            expired_count = _finalize_expired_opportunities(db, source)
            if expired_count:
                diagnostics.append(f"OCDS: {expired_count} procesos vencidos cerrados localmente")
            stale_count = _finalize_stale_peru_consultations(db, source, days=30)
            if stale_count:
                diagnostics.append(f"OCDS: {stale_count} procesos cerrados por consultas vencidas hace mas de 30 dias")
            existing_active = _existing_active_nomenclatures(db, source)
            raw = _filter_incremental_rows(raw, payload, existing_active, diagnostics)
            import pandas as pd

            requested_nomenclature = str(payload.get("nomenclature") or "").strip()
            is_automatic_run = bool(payload.get("automatic_incremental")) and not requested_nomenclature
            # Automatic scheduled runs skip this: re-injecting already-saved,
            # still-pending rows here is what used to send known processes back
            # into SEACE on every cycle. Manual revalidation (requested_nomenclature
            # set, or an explicit non-automatic search) still wants it.
            pending_rows = (
                []
                if is_automatic_run
                else _peru_pending_schedule_rows(
                    db,
                    source,
                    requested_nomenclature or keyword,
                    max_details,
                    allow_older=bool(requested_nomenclature),
                )
            )
            if pending_rows:
                raw = pd.concat([raw, pd.DataFrame(pending_rows)], ignore_index=True, sort=False)
                raw = raw.drop_duplicates(subset=["Nomenclatura"], keep="first")
                diagnostics.append(f"Cola SEACE por fin de consultas incorporada: {len(pending_rows)} procesos")
            update_progress(55, f"{len(raw)} coincidencias encontradas en OCDS")
            target_nomenclatures = _peru_schedule_targets(
                db,
                source,
                raw,
                allow_older=bool(requested_nomenclature),
                only_new=is_automatic_run,
            )
            if is_automatic_run:
                diagnostics.append(
                    f"Automático: solo procesos nuevos entran a SEACE ({len(target_nomenclatures)} nuevos)"
                )
            recent_rows = len(target_nomenclatures)
            # Save what OCDS already found right away - the SEACE step below is
            # slower and the one prone to proxy/browser interruptions. If it
            # never finishes, these opportunities (status "Revisar cronograma
            # SEACE", no proposal deadline yet) still land in the frontend for
            # manual "Revalidar fecha" instead of being silently lost.
            baseline_rows_found = _persist_peru_opportunities(
                db, raw, payload, ocds_keyword, max_results, source, run.id
            )
            if baseline_rows_found:
                diagnostics.append(f"OCDS guardado antes de SEACE: {baseline_rows_found} procesos")
            should_enrich_details = bool(payload.get("enrich_details", False)) or (
                recent_rows > 0
            )
            effective_max_details = max(max_details, recent_rows)
            if not target_nomenclatures and should_enrich_details and raw is not None and not raw.empty:
                # An explicit "leer detalles" toggle with no pending-schedule
                # queue: still enrich individually, picking whichever rows in
                # this result set have no proposal deadline yet.
                missing_mask = (
                    raw["propuesta_fin"].isna()
                    if "propuesta_fin" in raw.columns
                    else pd.Series([True] * len(raw), index=raw.index)
                )
                target_nomenclatures = [
                    str(value).strip()
                    for value in raw.loc[missing_mask, "Nomenclatura"].dropna().tolist()
                    if str(value).strip()
                ][:effective_max_details]
            if should_enrich_details and raw is not None and not raw.empty and target_nomenclatures:
                from src.seace_browser_scraper import search_seace_public_browser, search_seace_public_browser_targets

                details_year = str(selected_years[0] if selected_years else year or datetime.utcnow().year)
                raw_by_key: dict[str, Any] = {}
                for _, row in raw.iterrows():
                    key = _schedule_key(row.get("Nomenclatura", ""))
                    if key and key not in raw_by_key:
                        raw_by_key[key] = row
                seace_targets = []
                for nomenclature in target_nomenclatures[:effective_max_details]:
                    row = raw_by_key.get(_schedule_key(nomenclature))
                    description = str(row.get("Descripcion de Objeto") or "").strip() if row is not None else ""
                    seace_targets.append({
                        "nomenclature": nomenclature,
                        "keyword": (description or nomenclature)[:250],
                        "year": _year_for_nomenclature(nomenclature, details_year),
                    })
                seace_raw, seace_diagnostics = search_seace_public_browser_targets(
                    seace_targets,
                    version="Seace 3",
                    headless=True,
                    progress_callback=lambda value, message: update_progress(58 + value * 27, message),
                    cancel_callback=check_cancelled,
                )
                diagnostics.extend([f"OCDS detalle SEACE: {item}" for item in (seace_diagnostics or [])])
                if requested_nomenclature and not _seace_has_proposal_schedule(seace_raw, requested_nomenclature):
                    from backend.app.radar_config import DEFAULT_RADAR_KEYWORDS

                    target_row = raw[
                        raw["Nomenclatura"].fillna("").astype(str).str.strip().str.casefold()
                        == requested_nomenclature.casefold()
                    ]
                    searchable = " ".join(target_row.get("Descripcion de Objeto", pd.Series(dtype=str)).fillna("").astype(str))
                    fallback_keywords = [
                        candidate
                        for candidate in DEFAULT_RADAR_KEYWORDS
                        if contains_complete_phrase(searchable, candidate)
                    ]
                    for fallback_keyword in fallback_keywords:
                        diagnostics.append(f"SEACE exacto sin fin de propuesta; reintento por palabra: {fallback_keyword}")
                        fallback_raw, fallback_diagnostics = search_seace_public_browser(
                            keyword=fallback_keyword,
                            nomenclature="",
                            year=_year_for_nomenclature(requested_nomenclature, details_year),
                            version="Seace 3",
                            headless=True,
                            enrich_details=True,
                            max_details=1,
                            target_nomenclatures=[requested_nomenclature],
                            progress_callback=lambda value, message: update_progress(58 + value * 27, message),
                            cancel_callback=check_cancelled,
                        )
                        diagnostics.extend([f"OCDS detalle SEACE fallback: {item}" for item in (fallback_diagnostics or [])])
                        if _seace_has_proposal_schedule(fallback_raw, requested_nomenclature):
                            seace_raw = (
                                pd.concat([seace_raw, fallback_raw], ignore_index=True, sort=False)
                                if seace_raw is not None and not seace_raw.empty
                                else fallback_raw
                            )
                            break
                if recent_rows:
                    diagnostics.append(f"OCDS revalidacion automatica SEACE por consultas recientes: {recent_rows} procesos")
                raw = _merge_seace_schedule(raw, seace_raw, diagnostics)
            update_progress(86, "Priorizando oportunidades Perú")
            rows_found = _persist_peru_opportunities(db, raw, payload, ocds_keyword, max_results, source, run.id)
        else:
            raise RuntimeError(f"Fuente no soportada aun: {source}")

        run.rows_found = rows_found
        update_progress(92, "Guardando resultados")
        run.diagnostics = "\n".join([config_line, *(diagnostics or [])])
        run.status = "completed"
        run.progress = 100
        run.progress_message = "Búsqueda completada"
        run.finished_at = datetime.utcnow()
        db.commit()
        check_cancelled()
        evaluate_new_opportunity_alerts(db, run.id)
        evaluate_alerts(db)
        if settings.auto_send_alerts:
            send_pending_alerts(db)
    except RunCancelled:
        run.status = "cancelled"
        run.cancel_requested = True
        run.progress_message = "Búsqueda detenida"
        run.error_message = ""
        run.finished_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        run.status = "failed"
        run.progress_message = "La búsqueda no pudo completarse"
        run.error_message = f"{type(exc).__name__}: {exc}"
        run.diagnostics = traceback.format_exc(limit=8)
        run.finished_at = datetime.utcnow()
        db.commit()
    finally:
        if mercado_publico_lock_acquired:
            _mercado_publico_run_lock.release()
        _forget_cancel_event(run_id)
        db.close()
