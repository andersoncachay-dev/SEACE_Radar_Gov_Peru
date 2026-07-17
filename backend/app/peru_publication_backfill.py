from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, "/app")

import requests
from sqlalchemy import select

from src.keyword_matching import contains_any_complete_phrase
from src.oece_ocds_connector import API_BASE, _as_naive, _csv_col, _csv_date, _read_monthly_csv

from backend.app.database import SessionLocal
from backend.app.models import Opportunity
from backend.app.radar_config import DEFAULT_RADAR_KEYWORDS


def _key(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()


def main() -> None:
    db = SessionLocal()
    try:
        opportunities = list(
            db.scalars(
                select(Opportunity).where(
                    Opportunity.source == "oece_ocds_api",
                    Opportunity.is_archived.is_(False),
                )
            ).all()
        )
        targets = {_key(item.nomenclature or item.external_id): item for item in opportunities}
        authoritative: dict[str, dict[str, datetime | None]] = {}
        current = datetime.utcnow()
        default_map_path = "/app/backend/app/peru_publication_map.json"
        map_path = os.getenv("PERU_PUBLICATION_MAP_PATH", "").strip()
        if not map_path and os.path.exists(default_map_path):
            map_path = default_map_path
        if map_path:
            with open(map_path, "r", encoding="utf-8") as file:
                baked_map = json.load(file)
            for nomenclature, value in baked_map.items():
                payload = value if isinstance(value, dict) else {"publication_date": value}
                publication = _as_naive(payload.get("publication_date"))
                consultation = _as_naive(payload.get("consultation_deadline"))
                if publication is not None:
                    authoritative[_key(nomenclature)] = {
                        "publication_date": publication,
                        "consultation_deadline": consultation,
                    }
        skipped_months: list[int] = []
        for month in ([] if map_path else range(current.month, 0, -1)):
            try:
                frame, _ = _read_monthly_csv("seace_v3", current.year, month)
            except Exception:
                skipped_months.append(month)
                continue
            for _, row in frame.iterrows():
                nomenclature = _csv_col(
                    row,
                    "Entrega compilada:LicitaciÃ³n:TÃ­tulo de la licitaciÃ³n",
                    "Entrega compilada:LicitaciÃ³n:ID de licitaciÃ³n",
                    "Open Contracting ID",
                )
                key = _key(nomenclature)
                if key not in targets:
                    continue
                publication = _csv_date(
                    row,
                    "compiledRelease/tender/datePublished",
                    "Entrega compilada:Fecha de entrega",
                )
                if publication is not None:
                    authoritative[key] = {
                        "publication_date": publication,
                        "consultation_deadline": _csv_date(
                            row,
                            "Entrega compilada:Licitación:Periodo de consulta:Fecha de fin",
                        ),
                    }

        release_failures: list[str] = []
        session = requests.Session()
        session.headers.update({"User-Agent": "GovRadar CRM/1.0"})
        for key, item in targets.items():
            if key in authoritative:
                continue
            if map_path:
                continue
            searchable = " ".join((item.entity or "", item.nomenclature or "", item.description or ""))
            if not contains_any_complete_phrase(searchable, DEFAULT_RADAR_KEYWORDS):
                continue
            release_url = item.detail_url if "/api/v1/release/" in (item.detail_url or "") else ""
            if not release_url and item.release_id:
                release_url = f"{API_BASE}/release/{item.release_id}"
            if not release_url:
                release_failures.append(item.nomenclature or item.external_id)
                continue
            try:
                response = session.get(release_url, timeout=30)
                response.raise_for_status()
                payload = response.json()
                releases = payload.get("releases") or []
                release = releases[0] if releases else payload
                publication = _as_naive(
                    ((release.get("tender") or {}).get("datePublished")) or release.get("date")
                )
                if publication is not None:
                    tender = release.get("tender") or {}
                    authoritative[key] = {
                        "publication_date": publication,
                        "consultation_deadline": _as_naive((tender.get("enquiryPeriod") or {}).get("endDate")),
                    }
                else:
                    release_failures.append(item.nomenclature or item.external_id)
            except Exception:
                release_failures.append(item.nomenclature or item.external_id)

        changed = 0
        consultations_changed = 0
        statuses_changed = 0
        unmatched: list[str] = []
        for key, item in targets.items():
            schedule = authoritative.get(key)
            if schedule is None:
                unmatched.append(item.nomenclature or item.external_id)
                continue
            publication = schedule["publication_date"]
            if item.publication_date != publication:
                item.publication_date = publication
                changed += 1
            if item.schedule_source != "seace":
                consultation = schedule.get("consultation_deadline")
                if item.consultation_deadline != consultation:
                    item.consultation_deadline = consultation
                    consultations_changed += 1
                new_status = (
                    "Vigente para Consultas y Propuesta"
                    if consultation is not None and consultation >= current
                    else "Proceso Culminado"
                    if consultation is not None and consultation < current - timedelta(days=30)
                    else "Vigente para Propuesta"
                )
                if item.status != new_status:
                    item.status = new_status
                    statuses_changed += 1
                item.schedule_source = "ocds"
        db.commit()
        print(
            json.dumps(
                {
                    "country": "peru",
                    "total": len(opportunities),
                    "matched": len(authoritative),
                    "publication_dates_changed": changed,
                    "consultation_dates_changed": consultations_changed,
                    "statuses_changed": statuses_changed,
                    "unmatched": unmatched,
                    "skipped_months": skipped_months,
                    "release_failures": release_failures,
                    "map_path": map_path,
                },
                ensure_ascii=False,
            )
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
