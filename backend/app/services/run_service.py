from __future__ import annotations

import traceback
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import ScrapeRun, SearchProfile
from .ingestion_service import upsert_opportunities
from .notification_service import evaluate_alerts, evaluate_new_opportunity_alerts, send_pending_alerts


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

    try:
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
        config_line = (
            f"Configuracion: keyword={keyword} | max_resultados={max_results} | "
            f"leer_detalles={bool(payload.get('enrich_details', False))} | max_detalles={max_details}{period_text}"
        )

        run.status = "running"
        run.started_at = datetime.utcnow()
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
            )
            normalized = normalize_columns(raw) if raw is not None and not raw.empty else raw
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
            for mode, persisted_source in [
                ("licitaciones", "mercado_publico_browser"),
                ("grandes_compras", "mercado_publico_grandes_compras"),
            ]:
                try:
                    raw, mode_diagnostics = search_mercado_publico(
                        keyword=keyword,
                        mode=mode,
                        headless=True,
                        max_results=max_results,
                        enrich_details=bool(payload.get("enrich_details", False)) and mode == "licitaciones",
                        max_details=max_details,
                    )
                except Exception as exc:
                    mode_failures.append(f"{mode}: {type(exc).__name__}: {exc}")
                    all_diagnostics.append(f"Mercado Publico {mode}: fallo parcial ({type(exc).__name__}: {exc})")
                    continue
                normalized = normalize_columns(raw) if raw is not None and not raw.empty else raw
                normalized = _filter_dataframe_period(normalized, payload)
                enriched = enriquecer_oportunidades(normalized) if normalized is not None and not normalized.empty else normalized
                if enriched is not None and not enriched.empty and max_results:
                    enriched = enriched.head(max_results).copy()
                rows_found += upsert_opportunities(db, enriched, persisted_source, run_id=run.id)
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
            )
            normalized = normalize_columns(raw) if raw is not None and not raw.empty else raw
            if source.startswith("mercado_publico"):
                normalized = _filter_dataframe_period(normalized, payload)
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
            )
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
                )
                diagnostics.extend([f"OCDS detalle SEACE: {item}" for item in (seace_diagnostics or [])])
                if recent_rows:
                    diagnostics.append(f"OCDS revalidacion automatica SEACE por consultas recientes: {recent_rows} procesos")
                raw = _merge_seace_schedule(raw, seace_raw, diagnostics)
            normalized = normalize_columns(raw) if raw is not None and not raw.empty else raw
            enriched = enriquecer_oportunidades(normalized) if normalized is not None and not normalized.empty else normalized
            if enriched is not None and not enriched.empty and max_results:
                enriched = enriched.head(max_results).copy()
            rows_found = upsert_opportunities(db, enriched, source, run_id=run.id)
        else:
            raise RuntimeError(f"Fuente no soportada aun: {source}")

        run.rows_found = rows_found
        run.diagnostics = "\n".join([config_line, *(diagnostics or [])])
        run.status = "completed"
        run.finished_at = datetime.utcnow()
        db.commit()
        evaluate_new_opportunity_alerts(db, run.id)
        evaluate_alerts(db)
        if settings.auto_send_alerts:
            send_pending_alerts(db)
    except Exception as exc:
        run.status = "failed"
        run.error_message = f"{type(exc).__name__}: {exc}"
        run.diagnostics = traceback.format_exc(limit=8)
        run.finished_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()
