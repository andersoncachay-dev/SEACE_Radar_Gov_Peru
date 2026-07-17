from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
import unicodedata
from typing import Callable, List, Tuple
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait


BASE_URL = "https://www.mercadopublico.cl"
ADVANCED_SEARCH_URL = f"{BASE_URL}/portal/Modules/Site/Busquedas/BuscadorAvanzado.aspx?qs=1"
LARGE_PURCHASES_URL = f"{BASE_URL}/Portal/Modules/Site/Busquedas/BuscadorAvanzado.aspx?qs=9"


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", _clean(value))
    return text.encode("ascii", "ignore").decode("ascii").lower()


def _driver(headless: bool = True, download_dir: str | None = None):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1440,1100")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    if download_dir:
        options.add_experimental_option(
            "prefs",
            {
                "download.default_directory": download_dir,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True,
            },
        )
    driver = webdriver.Chrome(options=options)
    if download_dir:
        # Headless Chrome ignores the download prefs above unless downloads are
        # also allowed explicitly through DevTools for this session.
        driver.execute_cdp_cmd(
            "Page.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": download_dir},
        )
    return driver


def _set_search_text(driver, keyword: str) -> None:
    inputs = [item for item in driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input:not([type])") if item.is_displayed()]
    if not inputs:
        raise RuntimeError("Mercado Publico no mostro una caja de busqueda visible.")
    target = max(inputs, key=lambda item: item.size.get("width", 0))
    target.click()
    target.send_keys(Keys.CONTROL, "a")
    target.send_keys(Keys.BACKSPACE)
    target.send_keys(keyword)


def _click_search(driver) -> None:
    try:
        button = driver.find_element(By.ID, "btnBusqueda")
        if button.is_displayed():
            button.click()
            return
    except Exception:
        pass
    candidates = driver.find_elements(By.CSS_SELECTOR, "input[type='submit'], input[type='button'], input[type='image'], button")
    for item in candidates:
        label = _norm(item.get_attribute("value") or item.text or item.get_attribute("title") or "")
        if item.is_displayed() and "buscar" in label:
            item.click()
            return
    raise RuntimeError("No se encontro el boton Buscar en Mercado Publico.")


def _enable_regular_search_filters(
    driver,
    publication_date_from: str | None = None,
    publication_date_to: str | None = None,
    published_only: bool = False,
    date_filter_type: str = "publication",
) -> None:
    if publication_date_from or publication_date_to:
        checkbox = driver.find_element(By.ID, "chkFecha")
        if not checkbox.is_selected():
            checkbox.click()
        date_type_value = "2" if str(date_filter_type).strip().lower() == "closing" else "1"
        Select(driver.find_element(By.ID, "ddlDateType")).select_by_value(date_type_value)
        for element_id, value in (("txtFecha1", publication_date_from), ("txtFecha2", publication_date_to)):
            if not value:
                continue
            parsed = pd.to_datetime(value, errors="coerce")
            formatted = parsed.strftime("%d-%m-%Y") if not pd.isna(parsed) else value
            element = driver.find_element(By.ID, element_id)
            # Clicking opens an ASP.NET calendar overlay that intercepts the
            # second date field in headless Chrome. Set the value directly and
            # notify the page so its postback state remains consistent.
            driver.execute_script(
                "arguments[0].value = arguments[1];"
                "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
                element,
                formatted,
            )
    if published_only:
        checkbox = driver.find_element(By.ID, "chkEstado")
        if not checkbox.is_selected():
            checkbox.click()
        Select(driver.find_element(By.ID, "ddlAdquisitionState")).select_by_value("5")


def _wait_results(driver, keyword: str) -> None:
    try:
        WebDriverWait(driver, 25).until(
            lambda d: "resultadobusqueda" in d.current_url.lower()
            or "resultado de licitaciones" in _norm(d.page_source)
            or "resultado de grandes compras" in _norm(d.page_source)
        )
    except TimeoutException:
        if keyword.lower() not in driver.page_source.lower():
            raise RuntimeError("Mercado Publico no devolvio resultados en el tiempo esperado.")


def _find_excel_download_url(driver) -> str:
    for item in driver.find_elements(By.CSS_SELECTOR, "a"):
        if not item.is_displayed():
            continue
        onclick = item.get_attribute("onclick") or ""
        match = re.search(r"window\.open\('([^']*GrillaExcel\.aspx[^']*)'", onclick)
        if match:
            return urljoin(driver.current_url, match.group(1))
    return ""


def _excel_column(frame: pd.DataFrame, *labels: str) -> str | None:
    normalized = {_norm(str(column)): column for column in frame.columns}
    for label in labels:
        column = normalized.get(_norm(label))
        if column is not None:
            return column
    return None


def _download_excel_dataframe(driver, download_dir: str, timeout: float = 25.0) -> pd.DataFrame | None:
    """Returns None when Mercado Publico genuinely found nothing to export -
    a search with zero matches never renders the download link."""
    excel_url = _find_excel_download_url(driver)
    if not excel_url:
        if "no se encontraron" in _norm(driver.page_source):
            return None
        raise RuntimeError("No se encontro el enlace de descarga de Excel en Mercado Publico.")
    before = set(os.listdir(download_dir)) if os.path.isdir(download_dir) else set()
    driver.get(excel_url)
    deadline = time.time() + timeout
    downloaded_path = ""
    while time.time() < deadline:
        current = set(os.listdir(download_dir)) if os.path.isdir(download_dir) else set()
        candidates = [name for name in (current - before) if not name.endswith((".crdownload", ".tmp"))]
        if candidates:
            candidate_path = os.path.join(download_dir, candidates[0])
            size_before = os.path.getsize(candidate_path)
            time.sleep(0.5)
            if os.path.exists(candidate_path) and size_before > 0 and os.path.getsize(candidate_path) == size_before:
                downloaded_path = candidate_path
                break
        time.sleep(0.3)
    if not downloaded_path:
        raise RuntimeError("Mercado Publico no genero el archivo Excel a tiempo.")
    return pd.read_excel(downloaded_path)


def search_mercado_publico_bulk_excel(
    keyword: str,
    date_from: str,
    date_to: str,
    headless: bool = True,
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_callback: Callable[[], None] | None = None,
) -> Tuple[List[dict], List[str]]:
    """Discover every licitacion matching ``keyword`` within a Fecha de Cierre
    window in a single Excel download instead of paginating result pages.

    Mercado Publico's results table always exports "Fecha Cierre" regardless
    of which date-type filter was applied, so this always searches by closing
    date - callers translate any other selection into that same window.
    """
    diagnostics: List[str] = []
    download_dir = tempfile.mkdtemp(prefix="mp_excel_")
    driver = _driver(headless=headless, download_dir=download_dir)
    try:
        if cancel_callback:
            cancel_callback()
        if progress_callback:
            progress_callback(0.05, "Abriendo Mercado Publico: busqueda avanzada")
        driver.get(ADVANCED_SEARCH_URL)
        _set_search_text(driver, keyword)
        _enable_regular_search_filters(
            driver,
            publication_date_from=date_from,
            publication_date_to=date_to,
            published_only=False,
            date_filter_type="closing",
        )
        _click_search(driver)
        _wait_results(driver, keyword)
        time.sleep(1)
        if cancel_callback:
            cancel_callback()
        if progress_callback:
            progress_callback(0.35, "Descargando Excel de resultados")
        frame = _download_excel_dataframe(driver, download_dir)
        if frame is None:
            diagnostics.append(
                f"Mercado Publico licitaciones: 0 procesos para keyword={keyword} (cierre {date_from} a {date_to})"
            )
            if progress_callback:
                progress_callback(0.55, "0 procesos leidos del Excel")
            return [], diagnostics
        code_column = _excel_column(frame, "Numero", "Codigo")
        title_column = _excel_column(frame, "Nombre de la Licitacion")
        buyer_column = _excel_column(frame, "Comprador")
        status_column = _excel_column(frame, "Estado")
        closing_column = _excel_column(frame, "Fecha Cierre")
        diagnostics.append(
            f"Mercado Publico licitaciones: Excel con {len(frame)} procesos para keyword={keyword} "
            f"(cierre {date_from} a {date_to})"
        )
        rows: List[dict] = []
        for _, record in frame.iterrows():
            nomenclature = _clean(record.get(code_column, "")) if code_column else ""
            if not nomenclature:
                continue
            row = _empty_row("licitaciones")
            row["Nomenclatura"] = nomenclature
            row["Descripcion de Objeto"] = _clean(record.get(title_column, "")) if title_column else ""
            row["Nombre o Sigla de la Entidad"] = _clean(record.get(buyer_column, "")) if buyer_column else ""
            estado_ml = _clean(record.get(status_column, "")) if status_column else ""
            row["estado_mercado_publico"] = estado_ml
            row["Vigencia"] = estado_ml
            closing_value = record.get(closing_column) if closing_column else None
            closing_date = pd.to_datetime(closing_value, errors="coerce")
            row["propuesta_fin"] = closing_date.strftime("%d/%m/%Y %H:%M:%S") if not pd.isna(closing_date) else ""
            row["Estado Comercial"] = _estado_comercial(estado_ml, row["propuesta_fin"])
            rows.append(row)
        if progress_callback:
            progress_callback(0.55, f"{len(rows)} procesos leidos del Excel")
        return rows, diagnostics
    finally:
        driver.quit()
        shutil.rmtree(download_dir, ignore_errors=True)


def _href_to_url(href: str, current_url: str) -> str:
    href = _clean(href)
    if not href or href.startswith("javascript:"):
        return ""
    return urljoin(current_url or BASE_URL, href)


def _detail_link_url(link, current_url: str) -> str:
    if not link:
        return ""
    url = _href_to_url(link.get("href", ""), current_url)
    if url:
        return url
    onclick = link.get("onclick", "") or ""
    match = re.search(r"window\.open\('([^']+DetailsAcquisition\.aspx\?qs=[^']+)'", onclick, re.I)
    if match:
        return urljoin(current_url or BASE_URL, match.group(1))
    return ""


def _to_float(value: str) -> float:
    text = _clean(value).replace("$", "").replace("CLP", "").replace("Pesos", "")
    text = re.sub(r"[^0-9,.\-]", "", text)
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif text.count(".") > 1 or (text.count(".") == 1 and len(text.rsplit(".", 1)[1]) == 3):
        text = text.replace(".", "")
    elif text.count(",") > 1 or (text.count(",") == 1 and len(text.rsplit(",", 1)[1]) == 3):
        text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text) if text else 0.0
    except ValueError:
        return 0.0


def _date_from_chile(value: str) -> str:
    value = _clean(value)
    match = re.search(r"(\d{2})[-/](\d{2})[-/](\d{4})(?:\s+(\d{1,2}:\d{2}(?::\d{2})?))?", value)
    if not match:
        return value
    day, month, year, hour = match.groups()
    return f"{day}/{month}/{year} {hour or '23:59:00'}"


def _estado_comercial(state: str, closing: str, questions: str = "") -> str:
    state_norm = _norm(state)
    if any(value in state_norm for value in ("cerrada", "seleccionada", "adjudicada", "desierta", "revocada")):
        return "Proceso Culminado"
    now = pd.Timestamp.now()
    closing_date = pd.to_datetime(closing, errors="coerce", dayfirst=True)
    questions_date = pd.to_datetime(questions, errors="coerce", dayfirst=True)
    if not pd.isna(closing_date) and closing_date <= now:
        return "Proceso Culminado"
    if not pd.isna(questions_date) and questions_date > now:
        return "Vigente para Consultas y Propuesta"
    if not pd.isna(closing_date):
        return "Vigente para Propuesta"
    return "Revisar"


def _is_closed_process(row: dict) -> bool:
    state = _norm(row.get("Vigencia", ""))
    if any(value in state for value in ("cerrada", "seleccionada", "adjudicada", "desierta", "revocada")):
        return True
    closing = pd.to_datetime(row.get("propuesta_fin"), errors="coerce", dayfirst=True)
    return not pd.isna(closing) and closing.to_pydatetime() <= pd.Timestamp.now().to_pydatetime()


def _detail_row_indexes(
    rows: List[dict],
    enrich_details: bool,
    enrich_closed_details: bool,
    max_details: int,
) -> tuple[set[int], set[int]]:
    """Select active sheets for normal enrichment and closed sheets only on demand."""
    active_indexes = [index for index, row in enumerate(rows) if not _is_closed_process(row)]
    if not enrich_details:
        active_indexes = []
    elif max_details > 0:
        active_indexes = active_indexes[:max_details]
    closed_indexes = {
        index for index, row in enumerate(rows) if _is_closed_process(row)
    } if enrich_closed_details else set()
    return set(active_indexes), closed_indexes


def _filter_rows_for_period(rows: List[dict], years: List[int] | None, months: List[int] | None) -> List[dict]:
    selected_years = set(years or [])
    selected_months = set(months or [])
    if not selected_years and not selected_months:
        return rows
    filtered: List[dict] = []
    for row in rows:
        date = pd.to_datetime(
            row.get("Fecha y Hora de Publicacion") or row.get("convocatoria_inicio") or row.get("propuesta_fin"),
            errors="coerce",
            dayfirst=True,
        )
        if pd.isna(date):
            continue
        if selected_years and int(date.year) not in selected_years:
            continue
        if selected_months and int(date.month) not in selected_months:
            continue
        filtered.append(row)
    return filtered


def _empty_row(source: str) -> dict:
    row = {
        "RUC": "",
        "Nombre o Sigla de la Entidad": "",
        "Fecha y Hora de Publicacion": "",
        "Nomenclatura": "",
        "Objeto de Contratacion": "",
        "Descripcion de Objeto": "",
        "VR / VE / Cuantia de la contratacion": 0,
        "Moneda": "CLP",
        "Version SEACE": "Mercado Publico",
        "Estado Comercial": "",
        "Vigencia": "",
        "url_detalle": "",
        "Direccion Legal": "",
        "Telefono de la Entidad": "",
        "region": "Chile",
        "fuente_chile": source,
        "requerimiento_pdf": "",
        "documentos_texto": "",
    }
    for field in [
        "convocatoria_inicio",
        "convocatoria_fin",
        "registro_inicio",
        "registro_fin",
        "consulta_inicio",
        "consulta_fin",
        "absolucion_inicio",
        "absolucion_fin",
        "integracion_inicio",
        "integracion_fin",
        "propuesta_inicio",
        "propuesta_fin",
        "evaluacion_inicio",
        "evaluacion_fin",
        "buena_pro_inicio",
        "buena_pro_fin",
    ]:
        row[field] = ""
    return row


def _parse_regular_results(html: str, current_url: str) -> List[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: List[dict] = []
    for tr in soup.find_all("tr"):
        cells = [_clean(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
        cells = [cell for cell in cells if cell]
        if len(cells) < 5 or not re.match(r"^\d{3,}-\d+-[A-Z]{1,2}\d{2,3}$", cells[0]):
            continue
        row = _empty_row("licitaciones")
        row["Nomenclatura"] = cells[0]
        row["Descripcion de Objeto"] = cells[1]
        row["Nombre o Sigla de la Entidad"] = cells[2]
        row["propuesta_fin"] = _date_from_chile(cells[3])
        row["Vigencia"] = cells[4]
        row["Estado Comercial"] = _estado_comercial(cells[4], row["propuesta_fin"])
        link = tr.find("a")
        row["url_detalle"] = _detail_link_url(link, current_url)
        rows.append(row)
    return rows


def _parse_large_purchase_results(html: str, current_url: str) -> List[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: List[dict] = []
    for tr in soup.find_all("tr"):
        # Preserve empty cells: Mercado Publico leaves Proveedor blank in many
        # rows, and removing it shifts both invitation dates and the status.
        cells = [_clean(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
        if len(cells) < 7 or not re.match(r"^\d{3,}$", cells[0]):
            continue
        row = _empty_row("grandes_compras")
        row["Nomenclatura"] = cells[0]
        row["Descripcion de Objeto"] = cells[1]
        row["Nombre o Sigla de la Entidad"] = cells[2]
        row["convocatoria_inicio"] = _date_from_chile(cells[4])
        row["Fecha y Hora de Publicacion"] = row["convocatoria_inicio"]
        row["propuesta_fin"] = _date_from_chile(cells[5])
        row["Vigencia"] = cells[6] if len(cells) > 6 else ""
        row["Estado Comercial"] = _estado_comercial(row["Vigencia"], row["propuesta_fin"])
        link = tr.find("a")
        row["url_detalle"] = _detail_link_url(link, current_url)
        rows.append(row)
    return rows


def _parse_results_for_mode(mode: str, html: str, current_url: str) -> List[dict]:
    if mode == "grandes_compras":
        return _parse_large_purchase_results(html, current_url)
    return _parse_regular_results(html, current_url)


def _click_next_results_page(driver) -> bool:
    candidates = driver.find_elements(By.CSS_SELECTOR, "a, input[type='button'], input[type='submit'], button, div[onclick*='fnMovePage']")
    for item in candidates:
        try:
            label = _norm(item.text or item.get_attribute("value") or item.get_attribute("title") or "")
            href = _norm(item.get_attribute("href") or "")
            if not item.is_displayed():
                continue
            if "siguiente" not in label and "page$next" not in href:
                continue
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
            time.sleep(0.2)
            item.click()
            return True
        except Exception:
            continue
    return False


def _collect_result_rows(
    driver,
    mode: str,
    max_results: int,
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_callback: Callable[[], None] | None = None,
) -> List[dict]:
    rows: List[dict] = []
    seen: set[str] = set()
    visited_pages: set[str] = set()
    while True:
        if cancel_callback:
            cancel_callback()
        page_rows = _parse_results_for_mode(mode, driver.page_source, driver.current_url)
        for row in page_rows:
            key = row.get("Nomenclatura") or f"{row.get('Nombre o Sigla de la Entidad')}|{row.get('Descripcion de Objeto')}"
            if key and key not in seen:
                seen.add(key)
                rows.append(row)
                if max_results and len(rows) >= max_results:
                    return rows
        page_marker = "|".join(row.get("Nomenclatura", "") for row in page_rows) or driver.current_url
        if page_marker in visited_pages:
            return rows
        visited_pages.add(page_marker)
        if progress_callback:
            progress_callback(min(0.3, 0.1 + len(visited_pages) * 0.05), f"Leyendo página {len(visited_pages)} de {mode}")
        previous_marker = page_marker
        if not _click_next_results_page(driver):
            return rows
        try:
            WebDriverWait(driver, 20).until(
                lambda d: (
                    "|".join(row.get("Nomenclatura", "") for row in _parse_results_for_mode(mode, d.page_source, d.current_url))
                    or d.current_url
                )
                != previous_marker
            )
        except TimeoutException:
            return rows
        time.sleep(0.8)


def _find_date(text: str, labels: List[str]) -> str:
    for label in labels:
        pattern = re.compile(
            re.escape(label) + r"\s*:?\s*(\d{2}[-/]\d{2}[-/]\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)",
            re.I,
        )
        match = pattern.search(text)
        if match:
            return _clean(match.group(1))
    return ""


def _parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    text = _clean(soup.get_text(" ", strip=True))
    fields = {}
    region_match = re.search(
        r"Regi[oó]n en que se genera la licitaci[oó]n:\s*(.+?)(?=\s+(?:Subir|3\.\s*Etapas y plazos))",
        text,
        re.I,
    )
    publication = _find_date(text, ["Fecha de Publicacion", "Fecha de Publicación"])
    questions_end = _find_date(text, ["Fecha final de preguntas"])
    close_date = _find_date(text, ["Fecha de cierre de recepcion de la oferta", "Fecha de cierre de recepción de la oferta", "Fecha de Cierre"])
    adjudication = _find_date(text, ["Fecha de Adjudicacion", "Fecha de Adjudicación"])
    contract_duration_match = re.search(
        r"Tiempo del Contrato\s*:?\s*(.+?)(?=\s+(?:Plazos de pago|Opciones de pago|Subir))",
        text,
        re.I,
    )
    amount_match = re.search(
        r"(?:Monto\s+Total\s+Adjudicado|Monto\s+Adjudicado|Monto\s+Total\s+Estimado|"
        r"TOTAL\s+FINAL|Monto\s+estimado\s+para\s+la\s+gran\s+compra)"
        r"\s*:?\s*(?:CLP\s*)?\$?\s*([\d][\d.,]*)",
        text,
        re.I,
    )
    if publication:
        fields["Fecha y Hora de Publicacion"] = _date_from_chile(publication)
        fields["convocatoria_inicio"] = fields["Fecha y Hora de Publicacion"]
    if questions_end:
        fields["consulta_fin"] = _date_from_chile(questions_end)
    if close_date:
        fields["propuesta_fin"] = _date_from_chile(close_date)
    if adjudication:
        fields["buena_pro_fin"] = _date_from_chile(adjudication)
    if contract_duration_match:
        fields["contract_duration"] = _clean(contract_duration_match.group(1))
    if amount_match:
        fields["VR / VE / Cuantia de la contratacion"] = _to_float(amount_match.group(1))
    if region_match:
        fields["region"] = _clean(region_match.group(1))
    return fields


def _attachment_rows(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    docs = []
    for tr in soup.find_all("tr"):
        cells = [_clean(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
        joined = " ".join(cells)
        if len(cells) >= 3 and ("base" in _norm(joined) or ".pdf" in joined.lower() or ".doc" in joined.lower()):
            docs.append(joined)
    return docs


def _attachment_redirect_url(html: str, current_url: str) -> str:
    match = re.search(r"window\.location\.href\s*=\s*'([^']*ViewAttachmentLC\.aspx\?enc=[^']+)'", html)
    if match:
        return urljoin(current_url, match.group(1))
    return ""


def _click_first_containing(driver, text: str) -> bool:
    if _norm(text) == "ver adjuntos":
        try:
            button = driver.find_element(By.ID, "imgAdjuntos")
            if button.is_displayed():
                button.click()
                return True
        except Exception:
            pass
    target = _norm(text)
    for item in driver.find_elements(By.CSS_SELECTOR, "a, input, button, img"):
        label = _norm(item.text or item.get_attribute("value") or item.get_attribute("title") or item.get_attribute("alt") or "")
        if item.is_displayed() and target in label:
            item.click()
            return True
    return False


def _enrich_regular_detail(driver, row: dict, diagnostics: List[str], include_attachments: bool = True) -> dict:
    original = driver.current_window_handle
    original_url = driver.current_url
    before = set(driver.window_handles)
    link = None
    try:
        link = driver.find_element(By.LINK_TEXT, row["Nomenclatura"])
    except Exception:
        pass
    if not link and row.get("url_detalle"):
        driver.execute_script("window.open(arguments[0], '_blank')", row["url_detalle"])
    elif link:
        link.click()
    else:
        diagnostics.append(f"Sin enlace de detalle para {row['Nomenclatura']}")
        return row

    WebDriverWait(driver, 20).until(
        lambda d: len(set(d.window_handles) - before) > 0 or d.current_window_handle != original or d.current_url != original_url
    )
    new_handles = list(set(driver.window_handles) - before)
    if new_handles:
        driver.switch_to.window(new_handles[0])
    time.sleep(1)
    row.update(_parse_detail(driver.page_source))
    row["Estado Comercial"] = _estado_comercial(row.get("Vigencia", ""), row.get("propuesta_fin", ""), row.get("consulta_fin", ""))

    if include_attachments and _click_first_containing(driver, "Ver adjuntos"):
        time.sleep(1.5)
        if len(driver.window_handles) > len(before) + 1:
            attachment_handle = [h for h in driver.window_handles if h not in before and h != driver.current_window_handle][-1]
            driver.switch_to.window(attachment_handle)
        time.sleep(2)
        docs = _attachment_rows(driver.page_source)
        if not docs:
            redirect_url = _attachment_redirect_url(driver.page_source, driver.current_url)
            if redirect_url:
                driver.get(redirect_url)
                time.sleep(2)
                docs = _attachment_rows(driver.page_source)
        if docs:
            row["documentos_texto"] = " | ".join(docs[:10])
            base_docs = [doc for doc in docs if "base" in _norm(doc)]
            diagnostics.append(f"{row['Nomenclatura']}: {len(docs)} adjuntos detectados; bases={len(base_docs)}")
        else:
            diagnostics.append(f"{row['Nomenclatura']}: ficha con adjuntos sin enlaces descargables directos")
    for handle in list(driver.window_handles):
        if handle != original:
            driver.switch_to.window(handle)
            driver.close()
    driver.switch_to.window(original)
    if driver.current_url != original_url:
        driver.get(original_url)
    return row


def _open_detail_by_nomenclature(driver, nomenclature: str, original_handle: str) -> bool:
    """Search the exact process code (the API/CSV shortcuts on the ficha don't
    work) and open its detail page in a new tab. Returns True on success."""
    driver.get(ADVANCED_SEARCH_URL)
    _set_search_text(driver, nomenclature)
    _click_search(driver)
    _wait_results(driver, nomenclature)
    time.sleep(0.6)
    target = _norm(nomenclature)
    link = next(
        (item for item in driver.find_elements(By.CSS_SELECTOR, "a") if _norm(item.text) == target),
        None,
    )
    if link is None:
        return False
    before = set(driver.window_handles)
    link.click()
    try:
        WebDriverWait(driver, 15).until(
            lambda d: len(set(d.window_handles) - before) > 0 or d.current_window_handle != original_handle
        )
    except TimeoutException:
        return False
    new_handles = list(set(driver.window_handles) - before)
    if new_handles:
        driver.switch_to.window(new_handles[0])
    time.sleep(1)
    return True


def search_mercado_publico_details_by_code(
    nomenclatures: List[str],
    headless: bool = True,
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_callback: Callable[[], None] | None = None,
) -> Tuple[List[dict], List[str]]:
    """Enrich a specific set of already-known process codes one by one.

    Used for the rows that qualify for a ficha visit (Publicada, or whose
    Estado/Fecha Cierre changed since the last Excel snapshot) - not for
    bulk discovery, which goes through ``search_mercado_publico_bulk_excel``.
    """
    diagnostics: List[str] = []
    rows: List[dict] = []
    if not nomenclatures:
        return rows, diagnostics
    driver = _driver(headless=headless)
    original_handle = driver.current_window_handle
    total = len(nomenclatures)
    try:
        for index, nomenclature in enumerate(nomenclatures):
            if cancel_callback:
                cancel_callback()
            if progress_callback:
                progress_callback(index / max(total, 1), f"Leyendo ficha {index + 1}/{total}: {nomenclature}")
            try:
                opened = _open_detail_by_nomenclature(driver, nomenclature, original_handle)
                if not opened:
                    diagnostics.append(f"{nomenclature}: no se encontro la ficha por numero de proceso")
                    continue
                fields = _parse_detail(driver.page_source)
                fields["Nomenclatura"] = nomenclature
                fields["url_detalle"] = driver.current_url
                rows.append(fields)
            except Exception as exc:
                diagnostics.append(f"{nomenclature}: error leyendo ficha ({type(exc).__name__}: {exc})")
            finally:
                for handle in list(driver.window_handles):
                    if handle != original_handle:
                        try:
                            driver.switch_to.window(handle)
                            driver.close()
                        except Exception:
                            pass
                try:
                    driver.switch_to.window(original_handle)
                except Exception:
                    pass
        diagnostics.append(f"Mercado Publico fichas: {len(rows)}/{total} procesos enriquecidos")
    finally:
        driver.quit()
    return rows, diagnostics


def search_mercado_publico(
    keyword: str = "satelital",
    mode: str = "licitaciones",
    headless: bool = True,
    max_results: int = 25,
    enrich_details: bool = False,
    enrich_closed_details: bool = True,
    include_detail_attachments: bool = True,
    publication_date_from: str | None = None,
    publication_date_to: str | None = None,
    date_filter_type: str = "publication",
    include_active_revalidation: bool = False,
    max_details: int = 10,
    years: List[int] | None = None,
    months: List[int] | None = None,
    revalidation_rows: List[dict] | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_callback: Callable[[], None] | None = None,
) -> Tuple[pd.DataFrame, List[str]]:
    diagnostics: List[str] = []
    driver = _driver(headless=headless)
    try:
        if cancel_callback:
            cancel_callback()
        if progress_callback:
            progress_callback(0.05, f"Abriendo Mercado Público: {mode}")
        if mode == "grandes_compras":
            driver.get(LARGE_PURCHASES_URL)
            _set_search_text(driver, keyword)
            _click_search(driver)
        else:
            driver.get(ADVANCED_SEARCH_URL)
            _set_search_text(driver, keyword)
            _enable_regular_search_filters(
                driver,
                publication_date_from=publication_date_from,
                publication_date_to=publication_date_to,
                published_only=bool(publication_date_from or publication_date_to),
                date_filter_type=date_filter_type,
            )
            _click_search(driver)
        _wait_results(driver, keyword)
        time.sleep(1)
        rows = _collect_result_rows(driver, mode, max_results, progress_callback, cancel_callback)
        if mode == "licitaciones" and (publication_date_from or publication_date_to):
            for row in rows:
                row["automatic_discovery"] = True
        if mode == "licitaciones" and include_active_revalidation:
            driver.get(ADVANCED_SEARCH_URL)
            _set_search_text(driver, keyword)
            _enable_regular_search_filters(driver, published_only=True)
            _click_search(driver)
            _wait_results(driver, keyword)
            time.sleep(0.6)
            active_result_rows = _collect_result_rows(driver, mode, max_results, progress_callback, cancel_callback)
            by_key = {str(row.get("Nomenclatura", "")): row for row in rows}
            for row in active_result_rows:
                by_key.setdefault(str(row.get("Nomenclatura", "")), row)
            diagnostics.append(
                f"Mercado Publico licitaciones: {len(active_result_rows)} vigentes listados para revalidacion"
            )
            rows = list(by_key.values())
        if mode == "licitaciones" and revalidation_rows:
            by_key = {str(row.get("Nomenclatura", "")): row for row in rows}
            added = 0
            for row in revalidation_rows:
                key = str(row.get("Nomenclatura", ""))
                if key and key not in by_key:
                    by_key[key] = row
                    added += 1
            rows = list(by_key.values())
            diagnostics.append(
                f"Mercado Publico licitaciones: {added} fichas activas guardadas agregadas para revalidacion"
            )
        if progress_callback:
            progress_callback(0.35, f"{len(rows)} procesos detectados en {mode}")
        diagnostics.append(f"Mercado Publico {mode}: {len(rows)} procesos detectados para keyword={keyword} incluyendo paginas siguientes")
        if (years or months) and not (publication_date_from or publication_date_to):
            detected_count = len(rows)
            rows = _filter_rows_for_period(rows, years, months)
            diagnostics.append(
                f"Mercado Publico {mode}: {len(rows)}/{detected_count} procesos dentro del periodo solicitado"
            )
        elif publication_date_from or publication_date_to:
            date_label = "cierre" if str(date_filter_type).strip().lower() == "closing" else "publicacion"
            diagnostics.append(
                f"Mercado Publico {mode}: descubrimiento limitado por fecha de {date_label} "
                f"{publication_date_from or 'inicio'} a {publication_date_to or 'hoy'}"
            )

        if rows and mode == "licitaciones":
            explicit_indexes, closed_indexes = _detail_row_indexes(
                rows,
                enrich_details=enrich_details,
                enrich_closed_details=enrich_closed_details,
                max_details=max_details,
            )
            detail_indexes = sorted(explicit_indexes | closed_indexes)
            if closed_indexes:
                diagnostics.append(
                    f"Mercado Publico licitaciones: leyendo montos de {len(closed_indexes)} procesos cerrados"
                )
            total_details = max(1, len(detail_indexes))
            for position, index in enumerate(detail_indexes, start=1):
                if cancel_callback:
                    cancel_callback()
                try:
                    rows[index] = _enrich_regular_detail(
                        driver,
                        rows[index],
                        diagnostics,
                        include_attachments=include_detail_attachments and index in explicit_indexes,
                    )
                except Exception as exc:
                    if cancel_callback:
                        cancel_callback()
                    diagnostics.append(f"{rows[index].get('Nomenclatura', index)}: no se pudo enriquecer detalle ({type(exc).__name__}: {exc})")
                if progress_callback:
                    progress_callback(0.35 + (position / total_details) * 0.6, f"Revisando ficha {position} de {total_details}")
        if progress_callback:
            progress_callback(1.0, f"Consulta {mode} completada")
        return pd.DataFrame(rows), diagnostics
    finally:
        driver.quit()
