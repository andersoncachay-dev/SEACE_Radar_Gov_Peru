from __future__ import annotations

import re
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
from selenium.webdriver.support.ui import WebDriverWait


BASE_URL = "https://www.mercadopublico.cl"
ADVANCED_SEARCH_URL = f"{BASE_URL}/portal/Modules/Site/Busquedas/BuscadorAvanzado.aspx?qs=1"
LARGE_PURCHASES_URL = f"{BASE_URL}/Portal/Modules/Site/Busquedas/ResultadoBusqueda.aspx?qs=9"


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", _clean(value))
    return text.encode("ascii", "ignore").decode("ascii").lower()


def _driver(headless: bool = True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1440,1100")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=options)


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
    if questions:
        return "Vigente para Consultas y Propuesta"
    if closing:
        return "Vigente para Propuesta"
    return "Revisar"


def _is_closed_process(row: dict) -> bool:
    state = _norm(row.get("Vigencia", ""))
    if any(value in state for value in ("cerrada", "seleccionada", "adjudicada", "desierta", "revocada")):
        return True
    closing = pd.to_datetime(row.get("propuesta_fin"), errors="coerce", dayfirst=True)
    return not pd.isna(closing) and closing.to_pydatetime() <= pd.Timestamp.now().to_pydatetime()


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
        cells = [_clean(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
        cells = [cell for cell in cells if cell]
        if len(cells) < 6 or not re.match(r"^\d{3,}$", cells[0]):
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
    publication = _find_date(text, ["Fecha de Publicacion", "Fecha de Publicación"])
    questions_end = _find_date(text, ["Fecha final de preguntas"])
    close_date = _find_date(text, ["Fecha de cierre de recepcion de la oferta", "Fecha de cierre de recepción de la oferta", "Fecha de Cierre"])
    adjudication = _find_date(text, ["Fecha de Adjudicacion", "Fecha de Adjudicación"])
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
    if amount_match:
        fields["VR / VE / Cuantia de la contratacion"] = _to_float(amount_match.group(1))
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


def search_mercado_publico(
    keyword: str = "satelital",
    mode: str = "licitaciones",
    headless: bool = True,
    max_results: int = 25,
    enrich_details: bool = False,
    max_details: int = 10,
    years: List[int] | None = None,
    months: List[int] | None = None,
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
        else:
            driver.get(ADVANCED_SEARCH_URL)
            _set_search_text(driver, keyword)
            _click_search(driver)
        _wait_results(driver, keyword)
        time.sleep(1)
        rows = _collect_result_rows(driver, mode, max_results, progress_callback, cancel_callback)
        if progress_callback:
            progress_callback(0.35, f"{len(rows)} procesos detectados en {mode}")
        diagnostics.append(f"Mercado Publico {mode}: {len(rows)} procesos detectados para keyword={keyword} incluyendo paginas siguientes")
        if years or months:
            detected_count = len(rows)
            rows = _filter_rows_for_period(rows, years, months)
            diagnostics.append(
                f"Mercado Publico {mode}: {len(rows)}/{detected_count} procesos dentro del periodo solicitado"
            )

        if rows and mode == "licitaciones":
            explicit_limit = min(max_details or len(rows), len(rows)) if enrich_details else 0
            explicit_indexes = set(range(explicit_limit))
            closed_indexes = {index for index, row in enumerate(rows) if _is_closed_process(row)}
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
                        include_attachments=index in explicit_indexes,
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
