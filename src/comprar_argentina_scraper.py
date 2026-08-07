from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from io import BytesIO
from typing import Callable
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://comprar.gob.ar"
PROCESS_SEARCH_URL = f"{BASE_URL}/BuscarAvanzado.aspx"
PUBLICATION_SEARCH_URL = f"{BASE_URL}/BuscarAvanzadoPublicacion.aspx"
GRID_ID = "ctl00_CPH1_GridListaPliegos"
HEADERS = {"User-Agent": "SEACE-Radar/1.0 (public-procurement research)"}

PROVINCES = (
    "Ciudad de Buenos Aires",
    "Buenos Aires",
    "Catamarca",
    "Chaco",
    "Chubut",
    "Córdoba",
    "Corrientes",
    "Entre Ríos",
    "Formosa",
    "Jujuy",
    "La Pampa",
    "La Rioja",
    "Mendoza",
    "Misiones",
    "Neuquén",
    "Río Negro",
    "Salta",
    "San Juan",
    "San Luis",
    "Santa Cruz",
    "Santa Fe",
    "Santiago del Estero",
    "Tierra del Fuego",
    "Tucumán",
)


def _clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _norm(value: object) -> str:
    return unicodedata.normalize("NFKD", _clean(value)).encode("ascii", "ignore").decode().casefold()


def _hidden_fields(soup: BeautifulSoup) -> dict[str, str]:
    form = soup.find("form")
    if not form:
        raise RuntimeError("COMPR.AR no devolvió el formulario esperado.")
    return {
        field["name"]: field.get("value", "")
        for field in form.select("input[name][type=hidden]")
    }


def _post_search(
    session: requests.Session,
    url: str,
    keyword: str,
    kind: str,
    number: str = "",
) -> requests.Response:
    response = session.get(url, headers=HEADERS, timeout=45)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    payload = _hidden_fields(soup)
    if kind == "proceso":
        payload["ctl00$CPH1$txtNombrePliego"] = "" if number else keyword
        payload["ctl00$CPH1$txtNumeroProceso"] = number
        if number:
            payload["__EVENTTARGET"] = "ctl00$CPH1$btnListarPliegoNumero"
            payload["__EVENTARGUMENT"] = ""
        else:
            payload["ctl00$CPH1$btnListarPliegoAvanzado"] = "Buscar"
    else:
        payload["ctl00$CPH1$txtPublicacionObjeto"] = "" if number else keyword
        payload["ctl00$CPH1$txtNumeroPublicacion"] = number
        if number:
            payload["__EVENTTARGET"] = "ctl00$CPH1$btnListarPublicacionNumero"
            payload["__EVENTARGUMENT"] = ""
        else:
            payload["ctl00$CPH1$btnListarPublicacionAvanzado"] = "Buscar"
    result = session.post(url, data=payload, headers=HEADERS, timeout=75)
    result.raise_for_status()
    return result


def _postback(
    session: requests.Session,
    url: str,
    response: requests.Response,
    target: str,
    argument: str = "",
    timeout: int = 75,
) -> requests.Response:
    payload = _hidden_fields(BeautifulSoup(response.content, "html.parser"))
    payload["__EVENTTARGET"] = target
    payload["__EVENTARGUMENT"] = argument
    result = session.post(url, data=payload, headers=HEADERS, timeout=timeout)
    result.raise_for_status()
    return result


def _parse_date(value: object) -> pd.Timestamp | None:
    if isinstance(value, (datetime, pd.Timestamp)):
        return pd.Timestamp(value)
    text = re.sub(r"\bHrs?\.?", "", _clean(value), flags=re.IGNORECASE).strip()
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    return None if pd.isna(parsed) else parsed


def _province(*values: object) -> str:
    haystack = _norm(" ".join(_clean(value) for value in values))
    aliases = {
        "caba": "Ciudad de Buenos Aires",
        "capital federal": "Ciudad de Buenos Aires",
        "bariloche": "Río Negro",
        "viedma": "Río Negro",
        "la plata": "Buenos Aires",
        "mar del plata": "Buenos Aires",
        "bahia blanca": "Buenos Aires",
        "rosario": "Santa Fe",
        "rafaela": "Santa Fe",
        "posadas": "Misiones",
        "resistencia": "Chaco",
        "rawson": "Chubut",
        "trelew": "Chubut",
        "comodoro rivadavia": "Chubut",
        "ushuaia": "Tierra del Fuego",
        "rio grande": "Tierra del Fuego",
        "tierra del fuego": "Tierra del Fuego",
    }
    for alias, province in aliases.items():
        if alias in haystack:
            return province
    # Longest first prevents "Buenos Aires" from swallowing CABA-style text.
    for province in sorted(PROVINCES, key=len, reverse=True):
        if _norm(province) in haystack:
            return province
    return "Argentina"


def _commercial_status(source_status: object, opening_date: object = None) -> str:
    status = _norm(source_status)
    if status in {"adjudicado", "dejado sin efecto", "fracasado", "desierto"}:
        return "Proceso Culminado"
    if status == "publicado":
        opening = _parse_date(opening_date)
        return "Vigente para Propuesta" if opening is None or opening > pd.Timestamp.now() else "En Evaluación"
    if status:
        return "En Evaluación"
    return "Revisar estado COMPR.AR"


def _process_rows_from_excel(content: bytes) -> list[dict]:
    frame = pd.read_excel(BytesIO(content), engine="xlrd")
    rows: list[dict] = []
    for _, item in frame.iterrows():
        number = _clean(item.get("Número de Proceso"))
        if not number:
            continue
        opening = _parse_date(item.get("Fecha de apertura"))
        status = _clean(item.get("Estado"))
        unit = _clean(item.get("Unidad Ejecutora"))
        financial = _clean(item.get("Servicio Administrativo Financiero"))
        rows.append(
            {
                "nomenclatura": number,
                "expediente": _clean(item.get("Expediente")),
                "descripcion": _clean(item.get("Nombre proceso")),
                "objeto": _clean(item.get("Tipo proceso")),
                "fecha_apertura": opening,
                "propuesta_fin": opening,
                "estado_comprar": status,
                "source_status": status,
                "estado_comercial": _commercial_status(status, opening),
                "entidad": financial or unit,
                "contracting_unit": unit,
                "financial_service": financial,
                "region": _province(unit, financial),
                "record_type": "proceso",
                "moneda": "ARS",
                "monto": 0,
                "url_detalle": PROCESS_SEARCH_URL,
                "origen": "comprar_argentina_procesos",
            }
        )
    return rows


def _process_row_from_grid(item: dict[str, str]) -> dict:
    normalized = {_norm(key): value for key, value in item.items()}

    def value(label: str) -> str:
        return normalized.get(_norm(label), "")

    opening = _parse_date(value("Fecha de apertura"))
    status = value("Estado")
    unit = value("Unidad Ejecutora")
    financial = value("Servicio Administrativo Financiero")
    return {
        "nomenclatura": value("Número proceso"),
        "expediente": value("Expediente"),
        "descripcion": value("Nombre proceso"),
        "objeto": value("Tipo de Proceso"),
        "fecha_apertura": opening,
        "propuesta_fin": opening,
        "estado_comprar": status,
        "source_status": status,
        "estado_comercial": _commercial_status(status, opening),
        "entidad": financial or unit,
        "contracting_unit": unit,
        "financial_service": financial,
        "region": _province(unit, financial),
        "record_type": "proceso",
        "moneda": "ARS",
        "monto": 0,
        "url_detalle": PROCESS_SEARCH_URL,
        "origen": "comprar_argentina_procesos",
    }


def _grid_rows(response: requests.Response) -> list[dict[str, str]]:
    soup = BeautifulSoup(response.content, "html.parser")
    grid = soup.select_one(f"#{GRID_ID}")
    if not grid:
        return []
    headings = [_clean(cell.get_text(" ", strip=True)) for cell in grid.select("tr th")]
    rows: list[dict[str, str]] = []
    for tr in grid.select("tr"):
        cells = tr.find_all("td", recursive=False)
        if not cells or len(cells) < len(headings):
            continue
        values = [_clean(cell.get_text(" ", strip=True)) for cell in cells[: len(headings)]]
        record = dict(zip(headings, values))
        link = cells[0].find("a")
        record["_postback"] = link.get("href", "") if link else ""
        if any(values):
            rows.append(record)
    return rows


def _page_count(response: requests.Response) -> int:
    matches = re.findall(r"Page\$(\d+)", response.text)
    return max([1, *[int(value) for value in matches]])


def _next_publication_page(response: requests.Response, current_page: int) -> int | None:
    """Discover the next page from COMPR.AR's moving ASP.NET pager."""
    available = sorted({int(value) for value in re.findall(r"Page\$(\d+)", response.text)})
    next_page = current_page + 1
    return next_page if next_page in available else None


def _first_detail_url(session: requests.Session, search_url: str, response: requests.Response) -> str:
    soup = BeautifulSoup(response.content, "html.parser")
    grid = soup.select_one(f"#{GRID_ID}")
    link = grid.select_one("tr td a[href*='__doPostBack']") if grid else None
    match = re.search(r"__doPostBack\('([^']+)'\s*,\s*'([^']*)'\)", link.get("href", "") if link else "")
    if not match:
        return search_url
    detail = _postback(session, search_url, response, match.group(1), match.group(2), timeout=20)
    return detail.url if detail.url != search_url else search_url


def _process_schedule_from_detail(session: requests.Session, detail_url: str) -> dict[str, object]:
    """Read the public COMPR.AR schedule shown in an exact process sheet."""
    if not detail_url or detail_url == PROCESS_SEARCH_URL:
        return {}
    response = session.get(detail_url, headers=HEADERS, timeout=45)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")

    def date_value(id_suffix: str) -> pd.Timestamp | None:
        node = soup.select_one(f"[id$='{id_suffix}']")
        return _parse_date(node.get_text(" ", strip=True)) if node else None

    publication = date_value("Cronograma_lblFechaPublicacion")
    consultation_start = date_value("Cronograma_lblFechaInicioConsultas")
    consultation_end = date_value("Cronograma_lblFechaFinalConsultas")
    opening = date_value("Cronograma_lblFechaActoApertura")
    schedule = {
        "fecha_publicacion": publication,
        "consulta_inicio": consultation_start,
        "consulta_fin": consultation_end,
        "fecha_apertura": opening,
        "propuesta_fin": opening,
        "schedule_source": "comprar",
        "schedule_validated_at": datetime.utcnow(),
        "replace_schedule": True,
    }
    schedule["cronograma_texto"] = " | ".join(
        f"{label}: {value.strftime('%d/%m/%Y %H:%M')}"
        for label, value in (
            ("Publicacion", publication),
            ("Inicio consultas", consultation_start),
            ("Fin consultas", consultation_end),
            ("Acto de apertura", opening),
        )
        if value is not None
    )
    return schedule if any(value is not None for value in (publication, consultation_start, consultation_end, opening)) else {}


def _publication_schedule_from_detail(session: requests.Session, detail_url: str) -> dict[str, object]:
    """Read the cronograma rendered in an exact COMPR.AR publication sheet."""
    if not detail_url or detail_url == PUBLICATION_SEARCH_URL:
        return {}
    response = session.get(detail_url, headers=HEADERS, timeout=45)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    cronograma_heading = next(
        (
            heading
            for heading in soup.select(".panel-heading .panel-title")
            if _norm(heading.get_text(" ", strip=True)) == "cronograma"
        ),
        None,
    )
    panel = cronograma_heading.find_parent(class_="panel") if cronograma_heading else None
    if panel is None:
        return {}

    def date_value(label_for: str) -> pd.Timestamp | None:
        label = panel.select_one(f"label[for='{label_for}']")
        field = label.find_next(class_="form-control") if label else None
        if field is None:
            return None
        return _parse_date(field.get("value") or field.get_text(" ", strip=True))

    publication = date_value("FechaPublicacion")
    consultation_start = date_value("FechaInicioConsultas")
    consultation_end = date_value("FechaFinConsultas")
    opening = date_value("FechaApertura")
    reception_end = date_value("FechaFinRecepcionDocumentacion")
    schedule = {
        "fecha_publicacion": publication,
        "consulta_inicio": consultation_start,
        "consulta_fin": consultation_end,
        "fecha_apertura": opening,
        # Publicaciones gestionadas fuera del sistema use the end of document
        # reception as the commercial proposal deadline. It may differ from
        # the opening timestamp displayed alongside it in the sheet.
        "propuesta_fin": reception_end,
        "schedule_source": "comprar",
        "schedule_validated_at": datetime.utcnow(),
        "replace_schedule": True,
    }
    schedule["cronograma_texto"] = " | ".join(
        f"{label}: {value.strftime('%d/%m/%Y %H:%M')}"
        for label, value in (
            ("Publicacion", publication),
            ("Inicio consultas", consultation_start),
            ("Fin consultas", consultation_end),
            ("Fecha apertura", opening),
            ("Fin recepcion documentacion", reception_end),
        )
        if value is not None
    )
    return schedule if any(value is not None for value in (publication, consultation_start, consultation_end, opening, reception_end)) else {}


def _publication_row(item: dict[str, str]) -> dict:
    def value(*labels: str) -> str:
        normalized = {_norm(key): val for key, val in item.items()}
        for label in labels:
            if _norm(label) in normalized:
                return normalized[_norm(label)]
        return ""

    number = value("Número publicación", "Número proceso", "Número")
    opening_date = _parse_date(value("Fecha de apertura"))
    unit = value("Unidad Operativa de Contrataciones", "Unidad Ejecutora")
    financial = value("Servicio Administrativo Financiero")
    status = value("Estado") or "Publicado"
    return {
        "nomenclatura": number,
        "descripcion": value("Objeto", "Nombre publicación", "Nombre proceso"),
        "objeto": value("Tipo", "Tipo de publicación", "Tipo publicación", "Tipo de Proceso"),
        "fecha_publicacion": opening_date,
        "fecha_apertura": opening_date,
        "estado_comprar": status,
        "source_status": status,
        "estado_comercial": _commercial_status(status),
        "entidad": financial or unit,
        "contracting_unit": unit,
        "financial_service": financial,
        "region": _province(unit, financial),
        "record_type": "publicacion",
        "moneda": "ARS",
        "monto": 0,
        "url_detalle": PUBLICATION_SEARCH_URL,
        "origen": "comprar_argentina_publicaciones",
    }


def search_comprar_processes(
    keyword: str,
    max_results: int = 250,
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_callback: Callable[[], None] | None = None,
    nomenclature: str = "",
    enrich_details: bool = False,
    **_: object,
) -> tuple[pd.DataFrame, list[str]]:
    session = requests.Session()
    if cancel_callback:
        cancel_callback()
    if progress_callback:
        progress_callback(0.1, "Consultando procesos en COMPR.AR")
    result = _post_search(session, PROCESS_SEARCH_URL, keyword, "proceso", nomenclature)
    if nomenclature:
        rows = [_process_row_from_grid(item) for item in _grid_rows(result)]
        rows = [row for row in rows if row["nomenclatura"]]
        if rows and enrich_details:
            try:
                detail_url = _first_detail_url(session, PROCESS_SEARCH_URL, result)
                rows[0]["url_detalle"] = detail_url
                rows[0].update(_process_schedule_from_detail(session, detail_url))
            except requests.RequestException:
                pass
        return pd.DataFrame(rows[:max_results] if max_results else rows), [
            f"COMPR.AR procesos: {len(rows)} resultados para nomenclatura={nomenclature}"
        ]
    export = _postback(session, PROCESS_SEARCH_URL, result, "ctl00$CPH1$btnDescargarReporteExcel")
    if not export.content.startswith(bytes.fromhex("D0CF11E0")):
        raise RuntimeError("COMPR.AR no devolvió el reporte Excel de procesos esperado.")
    rows = _process_rows_from_excel(export.content)
    detail_url = ""
    if nomenclature and enrich_details:
        try:
            detail_url = _first_detail_url(session, PROCESS_SEARCH_URL, result)
        except requests.RequestException:
            detail_url = ""
    if detail_url and rows:
        rows[0]["url_detalle"] = detail_url
    if max_results:
        rows = rows[:max_results]
    if progress_callback:
        progress_callback(0.9, f"{len(rows)} procesos leídos del Excel")
    return pd.DataFrame(rows), [f"COMPR.AR procesos: {len(rows)} resultados para keyword={keyword}"]


def search_comprar_publications(
    keyword: str,
    max_results: int = 250,
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_callback: Callable[[], None] | None = None,
    nomenclature: str = "",
    enrich_details: bool = False,
    **_: object,
) -> tuple[pd.DataFrame, list[str]]:
    session = requests.Session()
    if progress_callback:
        progress_callback(0.1, "Consultando publicaciones en COMPR.AR")
    response = _post_search(session, PUBLICATION_SEARCH_URL, keyword, "publicacion", nomenclature)
    detail_url = ""
    if nomenclature and enrich_details:
        try:
            detail_url = _first_detail_url(session, PUBLICATION_SEARCH_URL, response)
        except requests.RequestException:
            detail_url = ""
    records: list[dict] = []
    page = 1
    while True:
        if cancel_callback:
            cancel_callback()
        records.extend(_publication_row(item) for item in _grid_rows(response))
        if progress_callback:
            progress_callback(min(0.9, 0.15 + 0.06 * page), f"Leyendo publicaciones: página {page}")
        if max_results and len(records) >= max_results:
            break
        next_page = _next_publication_page(response, page)
        if next_page is None:
            break
        response = _postback(
            session,
            PUBLICATION_SEARCH_URL,
            response,
            "ctl00$CPH1$GridListaPliegos",
            f"Page${next_page}",
        )
        page = next_page
    records = [
        row
        for row in records
        if row["nomenclatura"] and not re.fullmatch(r"\d+|\.{3}", row["nomenclatura"])
    ]
    records = list({row["nomenclatura"].casefold(): row for row in records}.values())
    if detail_url and records:
        records[0]["url_detalle"] = detail_url
        if enrich_details:
            try:
                records[0].update(_publication_schedule_from_detail(session, detail_url))
            except requests.RequestException:
                pass
    if max_results:
        records = records[:max_results]
    return pd.DataFrame(records), [f"COMPR.AR publicaciones: {len(records)} resultados para keyword={keyword}"]
