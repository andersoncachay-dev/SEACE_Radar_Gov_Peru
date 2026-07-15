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
from ..models import ScrapeRun, SearchProfile
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
    if not years and not months:
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
    return rows[mask].copy()


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


def _recent_consultation_rows(raw: Any, days: int = 30) -> int:
    if raw is None or getattr(raw, "empty", True) or "consulta_fin" not in raw.columns:
        return 0
    cutoff = datetime.utcnow() - timedelta(days=days)
    count = 0
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
        if isinstance(parsed, datetime) and parsed >= cutoff:
            count += 1
    return count


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
            normalized = _filter_dataframe_keyword(normalized, keyword)
            enriched = enriquecer_oportunidades(normalized) if normalized is not None and not normalized.empty else normalized
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
            for mode_index, (mode, persisted_source) in enumerate([
                ("licitaciones", "mercado_publico_browser"),
                ("grandes_compras", "mercado_publico_grandes_compras"),
            ]):
                stage_start = 5 + mode_index * 40
                try:
                    raw, mode_diagnostics = search_mercado_publico(
                        keyword=keyword,
                        mode=mode,
                        headless=True,
                        max_results=max_results,
                        enrich_details=bool(payload.get("enrich_details", False)) and mode == "licitaciones",
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
                normalized = _filter_dataframe_period(normalized, payload)
                normalized = _filter_dataframe_keyword(normalized, keyword)
                enriched = enriquecer_oportunidades(normalized) if normalized is not None and not normalized.empty else normalized
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
                max_details=max_details,
                years=sorted(_period_values(payload, "years", "year")),
                months=sorted(_period_values(payload, "months", "month")),
                progress_callback=lambda value, message: update_progress(5 + value * 75, message),
                cancel_callback=check_cancelled,
            )
            update_progress(82, "Procesando resultados de Mercado Público")
            normalized = normalize_columns(raw) if raw is not None and not raw.empty else raw
            if source.startswith("mercado_publico"):
                normalized = _filter_dataframe_period(normalized, payload)
            normalized = _filter_dataframe_keyword(normalized, keyword)
            enriched = enriquecer_oportunidades(normalized) if normalized is not None and not normalized.empty else normalized
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
            update_progress(55, f"{len(raw)} coincidencias encontradas en OCDS")
            recent_rows = _recent_consultation_rows(raw, days=30)
            should_enrich_details = bool(payload.get("enrich_details", False)) or recent_rows > 0
            effective_max_details = max(max_details, recent_rows)
            if should_enrich_details and raw is not None and not raw.empty and effective_max_details > 0:
                from src.seace_browser_scraper import search_seace_public_browser

                details_year = str(selected_years[0] if selected_years else year or datetime.utcnow().year)
                seace_raw, seace_diagnostics = search_seace_public_browser(
                    keyword=keyword,
                    year=details_year,
                    version="Seace 3",
                    headless=True,
                    enrich_details=True,
                    max_details=effective_max_details,
                    progress_callback=lambda value, message: update_progress(58 + value * 27, message),
                    cancel_callback=check_cancelled,
                )
                diagnostics.extend([f"OCDS detalle SEACE: {item}" for item in (seace_diagnostics or [])])
                if recent_rows:
                    diagnostics.append(f"OCDS revalidacion automatica SEACE por consultas recientes: {recent_rows} procesos")
                raw = _merge_seace_schedule(raw, seace_raw, diagnostics)
            update_progress(86, "Priorizando oportunidades Perú")
            normalized = normalize_columns(raw) if raw is not None and not raw.empty else raw
            normalized = _filter_dataframe_keyword(normalized, ocds_keyword)
            enriched = enriquecer_oportunidades(normalized) if normalized is not None and not normalized.empty else normalized
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
