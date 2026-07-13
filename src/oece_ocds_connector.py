from __future__ import annotations

import json
import zipfile
from io import BytesIO
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import pandas as pd
import requests


API_BASE = "https://contratacionesabiertas.oece.gob.pe/api/v1"
DEFAULT_SOURCES = ("seace_v3", "seace_v2")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_date(value: Any) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
        if pd.isna(parsed):
            return None
        return parsed.to_pydatetime()


def _as_naive(value: Any) -> datetime | None:
    parsed = _parse_date(value)
    if parsed is None:
        return None
    if parsed.tzinfo:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _contains_keyword(release: dict[str, Any], keyword: str) -> bool:
    if not keyword:
        return True
    tender = release.get("tender") or {}
    parts: list[str] = [
        release.get("ocid") or "",
        tender.get("id") or "",
        tender.get("title") or "",
        tender.get("description") or "",
        (tender.get("procuringEntity") or {}).get("name") or "",
        (release.get("buyer") or {}).get("name") or "",
    ]
    for item in tender.get("items") or []:
        parts.append(item.get("description") or "")
    for document in tender.get("documents") or []:
        parts.extend([document.get("title") or "", document.get("description") or "", document.get("documentType") or ""])
    return keyword.lower() in " ".join(parts).lower()


def _amount(tender: dict[str, Any]) -> tuple[float, str]:
    value = tender.get("value") or {}
    amount = value.get("amount_PEN", value.get("amount", 0)) or 0
    try:
        amount = float(amount)
    except Exception:
        amount = 0.0
    return amount, _clean(value.get("currency") or "PEN")


def _entity(release: dict[str, Any]) -> str:
    tender = release.get("tender") or {}
    return _clean((tender.get("procuringEntity") or {}).get("name") or (release.get("buyer") or {}).get("name"))


def _region(release: dict[str, Any]) -> str:
    buyer_name = _entity(release).lower()
    for party in release.get("parties") or []:
        if _clean(party.get("name")).lower() == buyer_name:
            address = party.get("address") or {}
            return _clean(address.get("department") or address.get("region") or address.get("locality"))
    return ""


def _ruc(release: dict[str, Any]) -> str:
    buyer_name = _entity(release).lower()
    for party in release.get("parties") or []:
        if _clean(party.get("name")).lower() != buyer_name:
            continue
        for identifier in party.get("additionalIdentifiers") or []:
            if "ruc" in _clean(identifier.get("scheme")).lower():
                return _clean(identifier.get("id"))
        identifier = party.get("identifier") or {}
        return _clean(identifier.get("id"))
    return ""


def _documents(tender: dict[str, Any]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for document in tender.get("documents") or []:
        url = _clean(document.get("url"))
        if not url:
            continue
        docs.append(
            {
                "title": _clean(document.get("title") or document.get("description") or "Documento OCDS"),
                "type": _clean(document.get("documentType") or "document"),
                "url": url,
                "published_at": _clean(document.get("datePublished") or document.get("dateModified")),
                "format": _clean(document.get("format")),
            }
        )
    return docs


def _first_document_url(documents: list[dict[str, Any]]) -> str:
    if not documents:
        return ""
    preferred = [
        doc
        for doc in documents
        if any(term in f"{doc.get('title','')} {doc.get('type','')}".lower() for term in ["base", "bidding", "convocatoria"])
    ]
    return _clean((preferred or documents)[0].get("url"))


def _commercial_status(tender: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    enquiry_end = _parse_date((tender.get("enquiryPeriod") or {}).get("endDate"))
    tender_status = _clean(tender.get("status")).lower()
    status_details = _clean(tender.get("statusDetails")).lower()
    if enquiry_end and enquiry_end.tzinfo is None:
        enquiry_end = enquiry_end.replace(tzinfo=timezone.utc)
    if enquiry_end and now <= enquiry_end:
        return "Vigente para Consultas y Propuesta"
    if any(term in f"{tender_status} {status_details}" for term in ["active", "convocado", "propuesta", "cotiz"]):
        return "Vigente para Propuesta"
    return "Proceso Culminado"


def _detail_url(release: dict[str, Any]) -> str:
    release_id = _clean(release.get("id"))
    if release_id:
        return urljoin(API_BASE + "/", f"release/{release_id}")
    ocid = _clean(release.get("ocid"))
    tender_id = _clean((release.get("tender") or {}).get("id"))
    source_id = _clean(release.get("sourceId"))
    if source_id and tender_id:
        return urljoin(API_BASE + "/", f"release/{source_id}/{tender_id}")
    return urljoin(API_BASE + "/", f"record/{ocid}") if ocid else ""


def _parse_release(release: dict[str, Any], source_id: str) -> dict[str, Any]:
    tender = release.get("tender") or {}
    docs = _documents(tender)
    amount, currency = _amount(tender)
    items = tender.get("items") or []
    item_description = " | ".join(_clean(item.get("description")) for item in items if _clean(item.get("description")))
    description = _clean(tender.get("description") or item_description)
    return {
        "RUC": _ruc(release),
        "Nombre o Sigla de la Entidad": _entity(release),
        "Fecha y Hora de Publicacion": _as_naive(tender.get("datePublished") or release.get("date")),
        "Nomenclatura": _clean(tender.get("title") or tender.get("id") or release.get("ocid")),
        "Objeto de Contratacion": _clean(tender.get("mainProcurementCategory") or tender.get("procurementMethodDetails")),
        "Descripcion de Objeto": description,
        "VR / VE / Cuantia de la contratacion": amount,
        "Moneda": currency,
        "Estado Comercial": _commercial_status(tender),
        "Vigencia": _clean(tender.get("statusDetails") or tender.get("status")),
        "url_detalle": _detail_url(release),
        "region": _region(release),
        "consulta_inicio": _as_naive((tender.get("enquiryPeriod") or {}).get("startDate")),
        "consulta_fin": _as_naive((tender.get("enquiryPeriod") or {}).get("endDate")),
        "propuesta_inicio": _as_naive((tender.get("tenderPeriod") or {}).get("startDate")),
        "propuesta_fin": _as_naive((tender.get("tenderPeriod") or {}).get("endDate")),
        "requerimiento_pdf": _first_document_url(docs),
        "documentos_ocds": json.dumps(docs, ensure_ascii=False),
        "ocid": _clean(release.get("ocid")),
        "tender_id": _clean(tender.get("id")),
        "source_id": source_id,
    }


def _fetch_releases(source_id: str, max_pages: int, page_size: int) -> tuple[list[dict[str, Any]], list[str]]:
    diagnostics: list[str] = []
    releases: list[dict[str, Any]] = []
    url = f"{API_BASE}/releases"
    params: dict[str, Any] = {"format": "json", "sourceId": source_id, "size": page_size}
    headers = {"User-Agent": "GovRadar CRM/1.0"}
    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            response = session.get(url, params=params, timeout=45, headers=headers)
            response.raise_for_status()
            payload = response.json()
            batch = payload.get("releases") or []
            releases.extend(batch)
            diagnostics.append(f"OCDS {source_id}: pagina {page} con {len(batch)} releases")
            next_url = (payload.get("links") or {}).get("next")
            if not next_url or not batch:
                break
            url = next_url
            params = {}
    return releases, diagnostics


def _read_monthly_csv(source_id: str, year: int, month: int) -> tuple[pd.DataFrame, list[str]]:
    diagnostics: list[str] = []
    file_url = f"{API_BASE}/file/{source_id}/csv/{year}/{month:02d}/es"
    response = requests.get(file_url, timeout=90, headers={"User-Agent": "GovRadar CRM/1.0"})
    response.raise_for_status()
    content = BytesIO(response.content)
    if not zipfile.is_zipfile(content):
        diagnostics.append(f"OCDS {source_id}: descarga CSV no comprimida o vacia")
        return pd.DataFrame(), diagnostics
    content.seek(0)
    with zipfile.ZipFile(content) as archive:
        registros_name = next((name for name in archive.namelist() if name.lower().endswith("registros.csv")), "")
        if not registros_name:
            diagnostics.append(f"OCDS {source_id}: no se encontro Registros.csv")
            return pd.DataFrame(), diagnostics
        with archive.open(registros_name) as file:
            df = pd.read_csv(file, dtype=str)
    diagnostics.append(f"OCDS {source_id}: descarga mensual {year}-{month:02d} con {len(df)} registros")
    return df, diagnostics


def _csv_col(row: pd.Series, *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value is not None and not pd.isna(value) and _clean(value):
            return _clean(value)
    return ""


def _csv_date(row: pd.Series, *names: str) -> datetime | None:
    value = _csv_col(row, *names)
    return _as_naive(value)


def _csv_amount(row: pd.Series) -> float:
    value = _csv_col(
        row,
        "compiledRelease/tender/value/amount_PEN",
        "Entrega compilada:Licitación:Valor:Monto",
        "Entrega compilada:Planeación:Presupuesto:Monto:Monto",
    )
    try:
        return float(str(value or "0").replace(",", ""))
    except Exception:
        return 0.0


def _csv_status(row: pd.Series) -> str:
    now = datetime.now(timezone.utc)
    consultation_end = _parse_date(_csv_col(row, "Entrega compilada:Licitación:Periodo de consulta:Fecha de fin"))
    tender_end = _parse_date(_csv_col(row, "Entrega compilada:Licitación:Periodo de licitación:Fecha de fin"))
    if consultation_end and consultation_end.tzinfo is None:
        consultation_end = consultation_end.replace(tzinfo=timezone.utc)
    if tender_end and tender_end.tzinfo is None:
        tender_end = tender_end.replace(tzinfo=timezone.utc)
    if consultation_end and now <= consultation_end:
        return "Vigente para Consultas y Propuesta"
    if tender_end and now <= tender_end:
        return "Vigente para Propuesta"
    return "Proceso Culminado"


def _csv_status(row: pd.Series) -> str:
    now = datetime.now(timezone.utc)
    consultation_end = _parse_date(_csv_col(row, "Entrega compilada:LicitaciÃ³n:Periodo de consulta:Fecha de fin"))
    if consultation_end and consultation_end.tzinfo is None:
        consultation_end = consultation_end.replace(tzinfo=timezone.utc)
    if consultation_end and now <= consultation_end:
        return "Vigente para Consultas y Propuesta"
    return "Proceso Culminado"


def _csv_matches(row: pd.Series, keyword: str) -> bool:
    if not keyword:
        return True
    all_values_haystack = " ".join(_clean(value) for value in row.values).lower()
    if keyword.lower() in all_values_haystack:
        return True
    haystack = " ".join(
        _csv_col(row, name)
        for name in [
            "Entrega compilada:Licitación:Título de la licitación",
            "Entrega compilada:Licitación:Descripción de la licitación",
            "Entrega compilada:Licitación:Entidad contratante:Nombre de la Organización",
            "Entrega compilada:Comprador:Nombre de la Organización",
            "Entrega compilada:Planeación:Presupuesto:Título del Proyecto",
        ]
    )
    return keyword.lower() in haystack.lower()


def _parse_csv_row(row: pd.Series, source_id: str) -> dict[str, Any]:
    release_id = _csv_col(row, "Entrega compilada:ID de Entrega")
    ocid = _csv_col(row, "Open Contracting ID", "Entrega compilada:Open Contracting ID")
    tender_id = _csv_col(row, "Entrega compilada:Licitación:ID de licitación")
    return {
        "RUC": _csv_col(row, "Entrega compilada:Licitación:Entidad contratante:ID de Organización", "Entrega compilada:Comprador:ID de Organización"),
        "Nombre o Sigla de la Entidad": _csv_col(row, "Entrega compilada:Licitación:Entidad contratante:Nombre de la Organización", "Entrega compilada:Comprador:Nombre de la Organización"),
        "Fecha y Hora de Publicacion": _csv_date(row, "compiledRelease/tender/datePublished", "Entrega compilada:Fecha de entrega"),
        "Nomenclatura": _csv_col(row, "Entrega compilada:Licitación:Título de la licitación", "Entrega compilada:Licitación:ID de licitación", "Open Contracting ID"),
        "Objeto de Contratacion": _csv_col(row, "Entrega compilada:Licitación:Categoría principal de contratación", "Entrega compilada:Licitación:Detalles del método de contratación"),
        "Descripcion de Objeto": _csv_col(row, "Entrega compilada:Licitación:Descripción de la licitación", "Entrega compilada:Planeación:Presupuesto:Título del Proyecto"),
        "VR / VE / Cuantia de la contratacion": _csv_amount(row),
        "Moneda": _csv_col(row, "Entrega compilada:Licitación:Valor:Moneda", "Entrega compilada:Planeación:Presupuesto:Monto:Moneda") or "PEN",
        "Estado Comercial": _csv_status(row),
        "Vigencia": _csv_col(row, "Entrega compilada:Licitación:Método de contratación", "Entrega compilada:Licitación:Detalles del método de contratación"),
        "url_detalle": urljoin(API_BASE + "/", f"release/{release_id}") if release_id else "",
        "region": "",
        "consulta_inicio": _csv_date(row, "Entrega compilada:Licitación:Periodo de consulta:Fecha de inicio"),
        "consulta_fin": _csv_date(row, "Entrega compilada:Licitación:Periodo de consulta:Fecha de fin"),
        "propuesta_inicio": _csv_date(row, "Entrega compilada:Licitación:Periodo de licitación:Fecha de inicio"),
        "propuesta_fin": _csv_date(row, "Entrega compilada:Licitación:Periodo de licitación:Fecha de fin"),
        "requerimiento_pdf": "",
        "documentos_ocds": "[]",
        "ocid": ocid,
        "tender_id": tender_id,
        "source_id": source_id,
        "release_id": release_id,
    }


def _search_monthly_downloads(
    keyword: str,
    max_results: int,
    sources: tuple[str, ...],
    *,
    year: int | None = None,
    month: int | None = None,
    years: list[int] | None = None,
    months: list[int] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    today = datetime.now()
    target_years = years or ([year] if year else [today.year])
    target_months = months or ([month] if month else [today.month])
    if not month and not months and today.month > 1:
        target_months.append(today.month - 1)
    diagnostics: list[str] = []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    limit = max_results if max_results and max_results > 0 else None
    for source_id in sources:
        for target_year in target_years:
            for target_month in target_months:
                try:
                    df, download_diagnostics = _read_monthly_csv(source_id, int(target_year), int(target_month))
                    diagnostics.extend(download_diagnostics)
                except Exception as exc:
                    diagnostics.append(f"OCDS {source_id}: error leyendo descarga {int(target_year)}-{int(target_month):02d}: {type(exc).__name__}: {exc}")
                    continue
                if df.empty:
                    continue
                matches = df[df.apply(lambda row: _csv_matches(row, keyword), axis=1)].copy()
                diagnostics.append(f"OCDS {source_id}: {len(matches)} coincidencias CSV para {keyword} en {int(target_year)}-{int(target_month):02d}")
                for _, row in matches.iterrows():
                    parsed = _parse_csv_row(row, source_id)
                    parsed["propuesta_inicio"] = None
                    parsed["propuesta_fin"] = None
                    unique_key = parsed.get("release_id") or parsed.get("ocid") or parsed.get("Nomenclatura")
                    if unique_key in seen:
                        continue
                    seen.add(unique_key)
                    rows.append(parsed)
                    if limit is not None and len(rows) >= limit:
                        return rows, diagnostics
    return rows, diagnostics


def search_oece_ocds(
    *,
    keyword: str = "satelital",
    year: int | None = None,
    month: int | None = None,
    years: list[int] | None = None,
    months: list[int] | None = None,
    max_results: int = 25,
    max_pages: int = 12,
    page_size: int = 100,
    sources: tuple[str, ...] = DEFAULT_SOURCES,
    allow_release_fallback: bool = False,
) -> tuple[pd.DataFrame, list[str]]:
    diagnostics: list[str] = [
        "Fuente: Portal de Contrataciones Abiertas OECE API OCDS",
        f"keyword={keyword}",
        f"periodo={','.join(map(str, years or [year or datetime.now().year]))}-{','.join(map(str, months or ([month] if month else ['actual+anterior'])))}",
        f"fuentes={','.join(sources)}",
    ]
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    download_rows, download_diagnostics = _search_monthly_downloads(
        keyword,
        max_results,
        sources,
        year=year,
        month=month,
        years=years,
        months=months,
    )
    diagnostics.extend(download_diagnostics)
    rows.extend(download_rows)
    seen.update(_clean(row.get("ocid") or row.get("release_id") or row.get("Nomenclatura")) for row in rows)
    limit = max_results if max_results and max_results > 0 else None
    if (limit is not None and len(rows) >= limit) or not allow_release_fallback:
        diagnostics.append(f"OCDS coincidencias normalizadas: {len(rows)}")
        return pd.DataFrame(rows), diagnostics

    for source_id in sources:
        releases, fetch_diagnostics = _fetch_releases(source_id, max_pages=max_pages, page_size=page_size)
        diagnostics.extend(fetch_diagnostics)
        for release in releases:
            if not _contains_keyword(release, keyword):
                continue
            row = _parse_release(release, source_id)
            unique_key = row.get("ocid") or f"{source_id}:{row.get('Nomenclatura')}"
            if unique_key in seen:
                continue
            seen.add(unique_key)
            rows.append(row)
            if limit is not None and len(rows) >= limit:
                break
        if limit is not None and len(rows) >= limit:
            break

    diagnostics.append(f"OCDS coincidencias normalizadas: {len(rows)}")
    return pd.DataFrame(rows), diagnostics
