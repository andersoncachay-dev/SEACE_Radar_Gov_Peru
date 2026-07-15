from __future__ import annotations

import traceback
import re
from datetime import datetime, timedelta
from threading import Event, Lock
from typing import Any

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
    date_column = "fecha_publicacion" if "fecha_publicacion" in rows.columns else "Fecha y Hora de Publicacion"
    if date_column not in rows.columns:
        return rows
    dates = rows[date_column]
    if getattr(dates, "isna", None) is not None and dates.isna().all() and "propuesta_fin" in rows.columns:
        dates = rows["propuesta_fin"]
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
            applied += 1
    diagnostics.append(f"OCDS cronograma SEACE aplicado por nomenclatura: {applied}/{len(merged)}")
    return merged


def _mercado_publico_modes(include_grandes_compras: bool) -> list[tuple[str, str]]:
    modes = [("licitaciones", "mercado_publico_browser")]
    if include_grandes_compras:
        modes.append(("grandes_compras", "mercado_publico_grandes_compras"))
    return modes


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
            period_text += (
                f" | publicados={payload.get('publication_date_from') or '-'}.."
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
        elif source == "mercado_publico_lmp_gc":
            from src.mercado_publico_scraper import search_mercado_publico
            from src.normalizer import normalize_columns
            from src.scoring import enriquecer_oportunidades

            rows_found = 0
            all_diagnostics = []
            mode_failures = []
            modes = _mercado_publico_modes(settings.enable_chile_grandes_compras)
            if not settings.enable_chile_grandes_compras:
                all_diagnostics.append(
                    "Mercado Publico grandes_compras: deshabilitado temporalmente; se consultaron solo licitaciones."
                )
            for mode_index, (mode, persisted_source) in enumerate(modes):
                stage_start = 5 + mode_index * 40
                existing_active = _existing_active_nomenclatures(db, persisted_source)
                expired_count = _finalize_expired_opportunities(db, persisted_source)
                if expired_count:
                    all_diagnostics.append(
                        f"Mercado Publico {mode}: {expired_count} procesos vencidos cerrados localmente"
                    )
                try:
                    raw, mode_diagnostics = search_mercado_publico(
                        keyword=keyword,
                        mode=mode,
                        headless=True,
                        max_results=max_results,
                        enrich_details=bool(payload.get("enrich_details", False)) and mode == "licitaciones",
                        enrich_closed_details=not bool(payload.get("skip_detail_enrichment", False)),
                        publication_date_from=payload.get("publication_date_from"),
                        publication_date_to=payload.get("publication_date_to"),
                        include_active_revalidation=bool(payload.get("automatic_incremental")) and mode == "licitaciones",
                        max_details=max_details,
                        years=sorted(_period_values(payload, "years", "year")),
                        months=sorted(_period_values(payload, "months", "month")),
                        progress_callback=lambda value, message, start=stage_start: update_progress(start + value * 35, message),
                        cancel_callback=check_cancelled,
                    )
                except RunCancelled:
                    raise
                except Exception as exc:
                    mode_failures.append(f"{mode}: {type(exc).__name__}: {exc}")
                    all_diagnostics.append(f"Mercado Publico {mode}: fallo parcial ({type(exc).__name__}: {exc})")
                    continue
                normalized = normalize_columns(raw) if raw is not None and not raw.empty else raw
                normalized = _filter_dataframe_entity(normalized, payload.get("entity_filter"))
                normalized = _filter_dataframe_nomenclature(normalized, payload.get("nomenclature"))
                normalized = _filter_incremental_rows(normalized, payload, existing_active, all_diagnostics)
                normalized = _filter_dataframe_keyword(normalized, keyword)
                from .scoring_config_service import get_scoring_config
                enriched = enriquecer_oportunidades(normalized, get_scoring_config(db, "chile")) if normalized is not None and not normalized.empty else normalized
                if enriched is not None and not enriched.empty and max_results:
                    enriched = enriched.head(max_results).copy()
                rows_found += upsert_opportunities(db, enriched, persisted_source, run_id=run.id)
                update_progress(stage_start + 38, f"Guardando resultados de {mode}")
                all_diagnostics.extend(mode_diagnostics or [])
            if rows_found == 0 and mode_failures:
                raise RuntimeError("Mercado Publico LMP-GC no devolvio resultados: " + " | ".join(mode_failures))
            diagnostics = all_diagnostics
        elif source in {"mercado_publico_browser", "mercado_publico_grandes_compras"}:
            from src.mercado_publico_scraper import search_mercado_publico
            from src.normalizer import normalize_columns
            from src.scoring import enriquecer_oportunidades

            mode = "grandes_compras" if source == "mercado_publico_grandes_compras" else "licitaciones"
            raw, diagnostics = search_mercado_publico(
                keyword=keyword,
                mode=mode,
                headless=True,
                max_results=max_results,
                enrich_details=bool(payload.get("enrich_details", False)),
                enrich_closed_details=not bool(payload.get("skip_detail_enrichment", False)),
                publication_date_from=payload.get("publication_date_from"),
                publication_date_to=payload.get("publication_date_to"),
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
            from src.normalizer import normalize_columns
            from src.oece_ocds_connector import search_oece_ocds
            from src.scoring import enriquecer_oportunidades

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
            existing_active = _existing_active_nomenclatures(db, source)
            expired_count = _finalize_expired_opportunities(db, source)
            if expired_count:
                diagnostics.append(f"OCDS: {expired_count} procesos vencidos cerrados localmente")
            raw = _filter_incremental_rows(raw, payload, existing_active, diagnostics)
            update_progress(55, f"{len(raw)} coincidencias encontradas en OCDS")
            recent_mask = _recent_consultation_mask(raw, days=30)
            recent_rows = sum(recent_mask)
            target_nomenclatures = (
                raw.loc[recent_mask, "Nomenclatura"].dropna().astype(str).tolist()
                if recent_mask and "Nomenclatura" in raw.columns
                else []
            )
            should_enrich_details = bool(payload.get("enrich_details", False)) or (
                recent_rows > 0 and not bool(payload.get("skip_detail_enrichment", False))
            )
            effective_max_details = max(max_details, recent_rows)
            if should_enrich_details and raw is not None and not raw.empty and effective_max_details > 0:
                from src.seace_browser_scraper import search_seace_public_browser

                details_year = str(selected_years[0] if selected_years else year or datetime.utcnow().year)
                seace_raw, seace_diagnostics = search_seace_public_browser(
                    keyword=keyword,
                    nomenclature=str(payload.get("nomenclature") or ""),
                    year=details_year,
                    version="Seace 3",
                    headless=True,
                    enrich_details=True,
                    max_details=effective_max_details,
                    target_nomenclatures=target_nomenclatures,
                    progress_callback=lambda value, message: update_progress(58 + value * 27, message),
                    cancel_callback=check_cancelled,
                )
                diagnostics.extend([f"OCDS detalle SEACE: {item}" for item in (seace_diagnostics or [])])
                if recent_rows:
                    diagnostics.append(f"OCDS revalidacion automatica SEACE por consultas recientes: {recent_rows} procesos")
                raw = _merge_seace_schedule(raw, seace_raw, diagnostics)
            update_progress(86, "Priorizando oportunidades Perú")
            normalized = normalize_columns(raw) if raw is not None and not raw.empty else raw
            normalized = _filter_dataframe_entity(normalized, payload.get("entity_filter"))
            normalized = _filter_dataframe_nomenclature(normalized, payload.get("nomenclature"))
            normalized = _filter_dataframe_keyword(normalized, ocds_keyword)
            from .scoring_config_service import get_scoring_config
            enriched = enriquecer_oportunidades(normalized, get_scoring_config(db, "peru")) if normalized is not None and not normalized.empty else normalized
            if enriched is not None and not enriched.empty and max_results:
                enriched = enriched.head(max_results).copy()
            rows_found = upsert_opportunities(db, enriched, source, run_id=run.id)
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
