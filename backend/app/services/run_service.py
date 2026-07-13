from __future__ import annotations

import traceback
from datetime import datetime

from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import ScrapeRun, SearchProfile
from .ingestion_service import upsert_opportunities
from .notification_service import evaluate_alerts, evaluate_new_opportunity_alerts, send_pending_alerts


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
        max_results = profile.max_results if profile else int(payload.get("max_results", 25))
        max_details = int(payload.get("max_details", min(max_results, 15)) or 0)
        config_line = (
            f"Configuracion: keyword={keyword} | max_resultados={max_results} | "
            f"leer_detalles={bool(payload.get('enrich_details', False))} | max_detalles={max_details}"
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
