
import gzip
import json
import tarfile
import zipfile
from io import BytesIO
from urllib.parse import urljoin
from typing import List, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup

DEFAULT_PORTAL_URL = "https://contratacionesabiertas.oece.gob.pe/api"
TIMEOUT = 90


def _abs(base, link):
    if not link:
        return None
    return urljoin(base.rstrip('/') + '/', link)


def _json_or_none(response):
    ctype = response.headers.get("content-type", "").lower()
    text = response.text.strip()[:1]
    if "json" in ctype or text in ["{", "["]:
        return response.json()
    return None


def _request(url):
    r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": "SEACE-Radar-Gov-Peru/0.4"})
    return r


def _flatten_file_list(payload, base_url):
    rows = []
    if isinstance(payload, dict):
        candidates = payload.get("files") or payload.get("data") or payload.get("results") or payload.get("items") or []
        if isinstance(candidates, dict):
            candidates = list(candidates.values())
    elif isinstance(payload, list):
        candidates = payload
    else:
        candidates = []
    for item in candidates:
        if isinstance(item, str):
            rows.append({"url": _abs(base_url, item), "name": item})
        elif isinstance(item, dict):
            row = dict(item)
            for k in ["url", "href", "link", "download_url", "downloadUrl"]:
                if k in row:
                    row["url"] = _abs(base_url, row[k])
                    break
            rows.append(row)
    return pd.DataFrame(rows)


def _extract_links_from_html(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for a in soup.find_all("a", href=True):
        href = a.get("href")
        text = a.get_text(" ", strip=True)
        if any(ext in href.lower() for ext in [".csv", ".xlsx", ".xls", ".json", ".jsonl", ".gz", ".zip", ".tar"]):
            rows.append({"name": text or href.split("/")[-1], "url": _abs(base_url, href)})
    return pd.DataFrame(rows)


def list_massive_files(base_url=DEFAULT_PORTAL_URL) -> Tuple[pd.DataFrame, List[str]]:
    diagnostics = []
    root = base_url.rstrip("/")
    candidates = [root + "/files", root.replace("/api", "") + "/files", root + "/api/files"]
    for url in candidates:
        try:
            r = _request(url)
            diagnostics.append(f"GET {url} -> {r.status_code} / {r.headers.get('content-type')}")
            payload = _json_or_none(r)
            if payload is not None:
                df = _flatten_file_list(payload, url)
                diagnostics.append(f"JSON list procesado: {len(df)} archivos")
                if not df.empty:
                    return df, diagnostics
            else:
                df = _extract_links_from_html(r.text, url)
                diagnostics.append(f"HTML links detectados: {len(df)} archivos")
                if not df.empty:
                    return df, diagnostics
        except Exception as e:
            diagnostics.append(f"Error {url}: {type(e).__name__} - {e}")
    return pd.DataFrame(), diagnostics


def _read_csv_bytes(content):
    for enc in ["utf-8", "latin-1", "cp1252"]:
        try:
            return pd.read_csv(BytesIO(content), encoding=enc, low_memory=False)
        except Exception:
            pass
    return pd.read_csv(BytesIO(content), low_memory=False)


def _read_from_zip(content):
    dfs = []
    with zipfile.ZipFile(BytesIO(content)) as z:
        names = z.namelist()
        for name in names:
            lower = name.lower()
            if lower.endswith(".csv"):
                dfs.append(_read_csv_bytes(z.read(name)))
            elif lower.endswith(".xlsx") or lower.endswith(".xls"):
                dfs.append(pd.read_excel(BytesIO(z.read(name)), engine="openpyxl"))
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def _read_from_targz(content):
    dfs = []
    with tarfile.open(fileobj=BytesIO(content), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            f = tar.extractfile(member)
            if not f:
                continue
            raw = f.read()
            lower = member.name.lower()
            if lower.endswith(".csv"):
                dfs.append(_read_csv_bytes(raw))
            elif lower.endswith(".jsonl") or lower.endswith(".ndjson"):
                dfs.append(_read_jsonl_bytes(raw))
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def _read_jsonl_bytes(content):
    rows = []
    for line in content.decode("utf-8", errors="ignore").splitlines():
        if line.strip():
            obj = json.loads(line)
            rows.append(_flatten_ocds_record(obj))
    return pd.DataFrame(rows)


def _flatten_ocds_record(obj):
    if "compiledRelease" in obj:
        obj = obj["compiledRelease"]
    tender = obj.get("tender") or {}
    buyer = obj.get("buyer") or {}
    value = tender.get("value") or {}
    period = tender.get("tenderPeriod") or {}
    return {
        "nomenclatura": obj.get("ocid") or obj.get("id"),
        "entidad": buyer.get("name") or (tender.get("procuringEntity") or {}).get("name"),
        "objeto": tender.get("mainProcurementCategory"),
        "descripcion": tender.get("description") or tender.get("title"),
        "monto": value.get("amount"),
        "fecha_publicacion": obj.get("date") or period.get("startDate"),
        "fecha_presentacion": period.get("endDate"),
        "estado": tender.get("status"),
        "url_detalle": obj.get("uri"),
    }


def download_any_dataset(url: str) -> Tuple[pd.DataFrame, str]:
    r = _request(url)
    content = r.content
    ctype = r.headers.get("content-type", "")
    lower = url.lower().split("?")[0]
    if r.status_code >= 400:
        raise ValueError(f"HTTP {r.status_code} al descargar {url}")
    if lower.endswith(".zip"):
        return _read_from_zip(content), f"ZIP descargado: {url}"
    if lower.endswith(".tar.gz") or lower.endswith(".tgz"):
        return _read_from_targz(content), f"TAR.GZ descargado: {url}"
    if lower.endswith(".gz"):
        content = gzip.decompress(content)
        lower = lower[:-3]
    if lower.endswith(".csv") or "csv" in ctype.lower():
        return _read_csv_bytes(content), f"CSV descargado: {url}"
    if lower.endswith(".xlsx") or lower.endswith(".xls") or "spreadsheet" in ctype.lower():
        return pd.read_excel(BytesIO(content), engine="openpyxl"), f"Excel descargado: {url}"
    if lower.endswith(".jsonl") or lower.endswith(".ndjson"):
        return _read_jsonl_bytes(content), f"JSONL descargado: {url}"
    if lower.endswith(".json") or "json" in ctype.lower():
        payload = json.loads(content.decode("utf-8"))
        if isinstance(payload, list):
            return pd.DataFrame([_flatten_ocds_record(x) for x in payload]), f"JSON descargado: {url}"
        if isinstance(payload, dict):
            records = payload.get("records") or payload.get("releases") or payload.get("data") or [payload]
            return pd.DataFrame([_flatten_ocds_record(x) for x in records if isinstance(x, dict)]), f"JSON descargado: {url}"
    # fallback tables
    try:
        tables = pd.read_html(BytesIO(content))
        if tables:
            return tables[0], f"HTML table descargada: {url}"
    except Exception:
        pass
    raise ValueError(f"Formato no reconocido desde {url}. Content-Type={ctype}")


def fetch_massive_by_params(base_url=DEFAULT_PORTAL_URL, source="ocds", file_type="csv", year="2026", month="") -> Tuple[pd.DataFrame, List[str]]:
    diagnostics = []
    root = base_url.rstrip("/")
    roots = [root, root.replace("/api", "")]
    months = [month] if str(month).strip() else ["", "0", "00", "all"]
    type_aliases = [file_type]
    if file_type == "excel":
        type_aliases += ["xlsx", "xls"]
    if file_type == "xlsx":
        type_aliases += ["excel", "xls"]
    if file_type == "csv":
        type_aliases += ["tar.gz", "gz"]

    tried = set()
    for base in roots:
        for t in type_aliases:
            for m in months:
                parts = [base, "file", source, t, str(year)]
                if str(m).strip():
                    parts.append(str(m))
                url = "/".join(p.strip("/") for p in parts)
                if not url.startswith("http"):
                    url = "https://" + url
                if url in tried:
                    continue
                tried.add(url)
                try:
                    diagnostics.append(f"Probando {url}")
                    df, msg = download_any_dataset(url)
                    diagnostics.append(msg)
                    if not df.empty:
                        diagnostics.append(f"Registros descargados: {len(df)}")
                        return df, diagnostics
                except Exception as e:
                    diagnostics.append(f"No funciono {url}: {type(e).__name__} - {e}")
    return pd.DataFrame(), diagnostics
