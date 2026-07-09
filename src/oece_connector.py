
import json
import gzip
from io import BytesIO
from typing import Dict, List, Tuple

import pandas as pd
import requests

DEFAULT_BASE_URL = "https://contratacionesabiertas.oece.gob.pe/api"
REQUEST_TIMEOUT = 30


def _flatten_release(release: Dict) -> Dict:
    tender = release.get("tender") or {}
    buyer = release.get("buyer") or {}
    value = tender.get("value") or {}
    period = tender.get("tenderPeriod") or {}
    procuring = tender.get("procuringEntity") or {}
    entidad = buyer.get("name") or procuring.get("name") or ""
    descripcion = tender.get("description") or tender.get("title") or ""
    return {
        "fuente": "OECE/OCDS",
        "nomenclatura": release.get("ocid") or release.get("id") or "",
        "entidad": entidad,
        "objeto": tender.get("mainProcurementCategory") or "",
        "descripcion": descripcion,
        "monto": value.get("amount") or 0,
        "moneda": value.get("currency") or "",
        "region": "",
        "fecha_publicacion": release.get("date") or period.get("startDate"),
        "fecha_presentacion": period.get("endDate"),
        "estado": tender.get("status") or "",
        "url_detalle": release.get("uri") or "",
    }


def _extract_releases(payload):
    if isinstance(payload, dict):
        if isinstance(payload.get("releases"), list):
            return payload["releases"]
        if isinstance(payload.get("records"), list):
            releases = []
            for record in payload["records"]:
                compiled = record.get("compiledRelease")
                if compiled:
                    releases.append(compiled)
                releases.extend(record.get("releases") or [])
            return releases
        if isinstance(payload.get("data"), list):
            return payload["data"]
        return [payload]
    if isinstance(payload, list):
        return payload
    return []


def _get_json(url, params=None):

    response = requests.get(
        url,
        params=params or {},
        timeout=30,
        headers={
            "User-Agent": "SEACE-Radar-Gov-Peru/0.3"
        },
    )

    print("URL:", response.url)
    print("STATUS:", response.status_code)
    print("CONTENT-TYPE:", response.headers.get("Content-Type"))
    print("BODY:", response.text[:500])

    response.raise_for_status()

    return response.json()


def fetch_ocds_releases(base_url=DEFAULT_BASE_URL, limit=100, keyword="", endpoint="auto") -> Tuple[pd.DataFrame, List[str]]:
    diagnostics = []
    endpoints = [endpoint] if endpoint != "auto" else [
        "/releases", "/api/releases", "/release-packages", "/api/release-packages",
        "/records", "/api/records", "/record-packages", "/api/record-packages",
    ]
    base_url = base_url.rstrip("/")
    all_rows = []
    for ep in endpoints:
        url = base_url + ep if ep.startswith("/") else ep
        try:
            payload = _get_json(url, params={"limit": limit})
            releases = _extract_releases(payload)
            rows = [_flatten_release(x) for x in releases if isinstance(x, dict)]
            if keyword:
                kw = keyword.lower()
                rows = [
                    r for r in rows
                    if kw in f"{r.get('entidad', '')} {r.get('descripcion', '')} {r.get('objeto', '')}".lower()
                ]
            diagnostics.append(f"OK {url}: {len(rows)} registros")
            all_rows.extend(rows)
            if rows:
                break
        except Exception as e:
            diagnostics.append(f"No disponible {url}: {type(e).__name__} - {e}")
    return pd.DataFrame(all_rows), diagnostics


def download_massive_dataset(url: str) -> Tuple[pd.DataFrame, str]:
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": "SEACE-Radar-Gov-Peru/0.3"},
    )
    response.raise_for_status()
    content = response.content
    lower = url.lower()
    if lower.endswith(".gz"):
        content = gzip.decompress(content)
        lower = lower[:-3]
    if lower.endswith(".csv"):
        return pd.read_csv(BytesIO(content)), "CSV descargado"
    if lower.endswith(".xlsx") or lower.endswith(".xls"):
        return pd.read_excel(BytesIO(content), engine="openpyxl"), "Excel descargado"
    if lower.endswith(".json"):
        payload = json.loads(content.decode("utf-8"))
        releases = _extract_releases(payload)
        return pd.DataFrame([_flatten_release(x) for x in releases if isinstance(x, dict)]), "JSON OCDS descargado"
    if lower.endswith(".jsonl") or lower.endswith(".ndjson"):
        rows = []
        for line in content.decode("utf-8", errors="ignore").splitlines():
            if line.strip():
                rows.append(_flatten_release(json.loads(line)))
        return pd.DataFrame(rows), "JSONL OCDS descargado"
    try:
        tables = pd.read_html(BytesIO(content))
        if tables:
            return tables[0], "Tabla HTML descargada"
    except Exception:
        pass
    raise ValueError("Formato no reconocido. Usa CSV, XLSX, JSON, JSONL o GZ publico.")
