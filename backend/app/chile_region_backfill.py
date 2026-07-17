from __future__ import annotations

import json
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from sqlalchemy import func, or_, select

from .database import SessionLocal
from .models import AppSetting, Opportunity


DETAIL_URL = "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={}"
REGIONS = {
    "arica y parinacota": "Arica y Parinacota",
    "tarapaca": "Tarapacá",
    "antofagasta": "Antofagasta",
    "atacama": "Atacama",
    "coquimbo": "Coquimbo",
    "valparaiso": "Valparaíso",
    "metropolitana de santiago": "Región Metropolitana de Santiago",
    "libertador general bernardo ohiggins": "Libertador General Bernardo O'Higgins",
    "ohiggins": "Libertador General Bernardo O'Higgins",
    "maule": "Maule",
    "nuble": "Ñuble",
    "biobio": "Biobío",
    "bio bio": "Biobío",
    "la araucania": "La Araucanía",
    "los rios": "Los Ríos",
    "los lagos": "Los Lagos",
    "aysen del general carlos ibanez del campo": "Aysén del General Carlos Ibáñez del Campo",
    "aysen": "Aysén del General Carlos Ibáñez del Campo",
    "magallanes y de la antartica chilena": "Magallanes y de la Antártica Chilena",
    "magallanes y antartica chilena": "Magallanes y de la Antártica Chilena",
}


def _normalized(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _canonical_region(value: str) -> str:
    normalized = _normalized(value)
    normalized = re.sub(r"^region\s+(?:de\s+|del\s+)?", "", normalized).strip()
    if normalized in REGIONS:
        return REGIONS[normalized]
    for key, region in sorted(REGIONS.items(), key=lambda item: len(item[0]), reverse=True):
        if key in normalized:
            return region
    return ""


def _fetch_region(item: dict[str, object]) -> dict[str, object]:
    code = str(item["nomenclature"] or item["external_id"] or "").strip()
    url = DETAIL_URL.format(quote(code, safe="-"))
    try:
        response = requests.get(
            url,
            timeout=35,
            headers={"User-Agent": "GovRadar/1.0 region-quality-backfill"},
        )
        response.raise_for_status()
        text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
        match = re.search(
            r"Regi[oó]n en que se genera la licitaci[oó]n:\s*(.+?)(?=\s+(?:Subir|3\.\s*Etapas y plazos))",
            text,
            re.IGNORECASE,
        )
        official = match.group(1).strip() if match else ""
        region = _canonical_region(official)
        return {**item, "previous_region": item["region"], "url": url, "official_region": official, "region": region, "error": "" if region else "region_not_found"}
    except Exception as exc:
        return {**item, "previous_region": item["region"], "url": url, "official_region": "", "region": "", "error": f"{type(exc).__name__}: {exc}"[:300]}


def main() -> None:
    apply_changes = os.getenv("APPLY_CHANGES", "false").strip().lower() == "true"
    db = SessionLocal()
    try:
        rows = db.execute(
            select(
                Opportunity.id,
                Opportunity.external_id,
                Opportunity.nomenclature,
                Opportunity.entity,
                Opportunity.region,
            ).where(
                Opportunity.source.like("mercado_publico%"),
                Opportunity.is_archived.is_(False),
                or_(
                    func.trim(Opportunity.region) == "",
                    func.lower(func.trim(Opportunity.region)) == "chile",
                ),
            ).order_by(Opportunity.id)
        ).all()
        candidates = [dict(row._mapping) for row in rows]
        results: list[dict[str, object]] = []
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(_fetch_region, item) for item in candidates]
            for future in as_completed(futures):
                results.append(future.result())
        results.sort(key=lambda item: int(item["id"]))
        resolved = [item for item in results if item["region"]]
        unresolved = [item for item in results if not item["region"]]
        audit = {
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "source": "MercadoPublico.cl ficha oficial",
            "applied": apply_changes,
            "candidates": len(candidates),
            "resolved": len(resolved),
            "unresolved": len(unresolved),
            "changes": [
                {
                    "id": item["id"],
                    "external_id": item["external_id"],
                    "previous_region": item["previous_region"],
                    "new_region": item["region"],
                    "official_region": item["official_region"],
                    "url": item["url"],
                }
                for item in resolved
            ],
            "unresolved_items": [
                {"id": item["id"], "external_id": item["external_id"], "url": item["url"], "error": item["error"]}
                for item in unresolved
            ],
        }
        if apply_changes:
            by_id = {int(item["id"]): str(item["region"]) for item in resolved}
            opportunities = db.scalars(select(Opportunity).where(Opportunity.id.in_(by_id))).all()
            for opportunity in opportunities:
                opportunity.region = by_id[opportunity.id]
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            db.add(AppSetting(key=f"audit.chile_region_backfill.{stamp}", value=json.dumps(audit, ensure_ascii=False)))
            db.commit()
        print(json.dumps(audit, ensure_ascii=False))
    finally:
        db.close()


if __name__ == "__main__":
    main()
