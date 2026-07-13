from __future__ import annotations

import mimetypes
import re
import time
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Document, Opportunity

try:
    from src.seace_browser_scraper import (
        PROCESS_FORM,
        SEACE_PUBLIC_URL,
        _click_like_user,
        _set_input_like_user,
    )
except Exception:  # pragma: no cover - fallback for packaged deployments without src helpers
    PROCESS_FORM = "tbBuscador:idFormBuscarProceso"
    SEACE_PUBLIC_URL = "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml"
    _click_like_user = None
    _set_input_like_user = None

DOCUMENT_ROOT = Path("exports") / "documents"


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _safe_filename(value: str, fallback: str = "documento") -> str:
    name = unquote(str(value or "")).strip()
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return (name[:180] or fallback)


def _filename_from_url(url: str, title: str, opportunity: Opportunity) -> str:
    parsed = urlparse(url or "")
    name = Path(unquote(parsed.path)).name
    if not name or "." not in name:
        name = title or opportunity.nomenclature or opportunity.external_id or "documento"
    return _safe_filename(name)


def _register_document(
    db: Session,
    opportunity: Opportunity,
    *,
    title: str,
    source_url: str = "",
    local_path: str = "",
    filename: str = "",
    status: str = "registered",
    error_message: str = "",
) -> Document:
    filename = filename or (_filename_from_url(source_url, title, opportunity) if source_url else _safe_filename(title))
    mime_type = mimetypes.guess_type(filename)[0] or ""
    existing = None
    if source_url:
        existing = db.scalar(
            select(Document).where(
                Document.opportunity_id == opportunity.id,
                Document.source_url == source_url,
            )
        )
    doc = existing or Document(opportunity_id=opportunity.id)
    doc.title = _clean(title)[:255]
    doc.document_type = Path(filename).suffix.lower().replace(".", "")
    doc.source_url = source_url
    doc.local_path = local_path
    doc.filename = filename[:255]
    doc.mime_type = mime_type
    doc.status = status
    doc.error_message = error_message
    if not existing:
        db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _register_local_download(db: Session, opportunity: Opportunity, path: Path, title: str, source_url: str = "") -> Document:
    return _register_document(
        db,
        opportunity,
        title=title,
        source_url=source_url,
        local_path=str(path),
        filename=path.name,
        status="downloaded",
    )


def _nomenclature(opportunity: Opportunity) -> str:
    return _clean(opportunity.nomenclature or opportunity.external_id)


def _search_keyword(opportunity: Opportunity) -> str:
    text = _clean(f"{opportunity.description or ''} {opportunity.nomenclature or ''}")
    normalized = (
        text.lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )
    for phrase in [
        "radio enlace",
        "internet satelital",
        "fibra optica",
        "telefonia movil satelital",
        "geolocalizacion satelital",
        "kit de conectividad",
        "conectividad a internet",
    ]:
        if phrase in normalized:
            return phrase.upper()
    match = re.search(r"((?:\w+\s+){0,3}satelital(?:\s+\w+){0,3})", normalized)
    if match:
        return match.group(1).strip().upper()
    for keyword in ["satelital", "conectividad", "internet", "fibra"]:
        if keyword in normalized:
            return keyword
    words = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{5,}", opportunity.description or "")
    return words[0] if words else "satelital"


def _process_year(opportunity: Opportunity) -> str:
    if opportunity.publication_date:
        return str(opportunity.publication_date.year)
    match = re.search(r"\b(20\d{2})\b", _nomenclature(opportunity))
    return match.group(1) if match else "2026"


def _page_has_process_data(driver, opportunity: Opportunity) -> bool:
    text = _clean(driver.execute_script("return document.body ? document.body.innerText : ''") or "")
    nomen = _nomenclature(opportunity)
    return bool(nomen and nomen in text and "No se encontraron Datos" not in text)


def _find_row_action_by_nomenclature(driver, nomenclature: str):
    return driver.execute_script(
        r"""
        const nomen = String(arguments[0] || '').trim();
        function clean(s){return (s||'').replace(/\s+/g,' ').trim();}
        for(const tr of Array.from(document.querySelectorAll('tr'))){
            const cells = Array.from(tr.querySelectorAll(':scope > td, :scope > th')).map(td => clean(td.innerText));
            if(cells.length < 8) continue;
            if(!/^\d{1,4}$/.test(cells[0] || '')) continue;
            if(!cells.some(cell => cell.includes(nomen))) continue;
            const clickables = Array.from(tr.querySelectorAll('a,button,img,span.ui-icon'));
            for(let i=clickables.length - 1; i>=0; i--){
                const el = clickables[i];
                const merged = clean((el.innerText||'')+' '+(el.title||'')+' '+(el.alt||'')+' '+(el.getAttribute('href')||'')+' '+(el.getAttribute('onclick')||'')+' '+el.className).toLowerCase();
                if(merged.includes('fichaseleccion') || merged.includes('detalle') || merged.includes('ver') || merged.includes('search') || merged.includes('grafichasel')){
                    return el;
                }
            }
            return clickables[clickables.length - 1] || null;
        }
        return null;
        """,
        nomenclature,
    )


def _click_paginator(driver, selector: str) -> bool:
    element = driver.execute_script(
        """
        const paginator = Array.from(document.querySelectorAll('.ui-paginator'))
            .find(el => (el.id || '').includes('idFormBuscarProceso:dtProcesos'));
        const el = paginator ? paginator.querySelector(arguments[0]) : null;
        if(!el) return null;
        if((el.className || '').includes('ui-state-disabled')) return null;
        return el;
        """,
        selector,
    )
    if element is None:
        return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        ActionChains(driver).move_to_element(element).pause(0.1).click(element).perform()
    except Exception:
        driver.execute_script("arguments[0].click();", element)
    return True


def _locate_search_result_page(driver, nomenclature: str) -> bool:
    def contains_target() -> bool:
        text = driver.execute_script("return document.body ? document.body.innerText : ''") or ""
        return nomenclature in text

    _click_paginator(driver, ".ui-paginator-first")
    time.sleep(2)
    for _ in range(20):
        if contains_target():
            return True
        if not _click_paginator(driver, ".ui-paginator-next"):
            return False
        time.sleep(2)
    return False


def _open_detail_from_search(driver, opportunity: Opportunity) -> bool:
    if not (_set_input_like_user and _click_like_user):
        return False
    nomen = _nomenclature(opportunity)
    if not nomen:
        return False

    driver.get(SEACE_PUBLIC_URL)
    time.sleep(3)
    tabs = driver.find_elements(By.XPATH, "//*[contains(text(),'Buscador de Procedimientos de Selecci')]")
    if tabs:
        driver.execute_script("arguments[0].click();", tabs[0])
        time.sleep(3)

    wait = WebDriverWait(driver, 45)
    wait.until(EC.presence_of_element_located((By.ID, f"{PROCESS_FORM}:descripcionObjeto")))
    driver.execute_script("const active=document.getElementById('tbBuscador_activeIndex'); if(active) active.value='1';")
    _set_input_like_user(driver, f"{PROCESS_FORM}:descripcionObjeto", _search_keyword(opportunity))
    _set_input_like_user(driver, f"{PROCESS_FORM}:anioConvocatoria_input", _process_year(opportunity))
    _set_input_like_user(driver, f"{PROCESS_FORM}:anioConvocatoria_focus", _process_year(opportunity))
    _set_input_like_user(driver, f"{PROCESS_FORM}:j_idt247_input", "3")
    clicked = _click_like_user(driver, f"{PROCESS_FORM}:btnBuscarSelToken") or _click_like_user(driver, f"{PROCESS_FORM}:btnBuscarSel")
    if not clicked:
        return False

    def wait_for_grid() -> bool:
        deadline = time.time() + 45
        while time.time() < deadline:
            text = driver.execute_script("return document.body ? document.body.innerText : ''") or ""
            if "Nomenclatura" in text and "Descripción de Objeto" in text:
                return True
            time.sleep(1)
        return False

    if not wait_for_grid():
        _click_like_user(driver, f"{PROCESS_FORM}:btnBuscarSel")
        if not wait_for_grid():
            return False
    if not _locate_search_result_page(driver, nomen):
        return False

    action = _find_row_action_by_nomenclature(driver, nomen)
    if action is None:
        return False
    before = set(driver.window_handles)
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", action)
    time.sleep(0.4)
    try:
        ActionChains(driver).move_to_element(action).pause(0.1).click(action).perform()
    except Exception:
        driver.execute_script("arguments[0].click();", action)
    time.sleep(5)
    new_handles = list(set(driver.window_handles) - before)
    if new_handles:
        driver.switch_to.window(new_handles[-1])
    deadline = time.time() + 20
    while time.time() < deadline:
        if "fichaSeleccion" in driver.current_url and _page_has_process_data(driver, opportunity):
            return True
        time.sleep(1)
    return False


def _download_direct(db: Session, opportunity: Opportunity, url: str, title: str, cookies=None, referer: str = "") -> Document:
    target_dir = DOCUMENT_ROOT / str(opportunity.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = _filename_from_url(url, title, opportunity)
    target = target_dir / filename
    try:
        session = requests.Session()
        if cookies:
            for cookie in cookies:
                session.cookies.set(cookie.get("name"), cookie.get("value"), domain=cookie.get("domain"))
        response = session.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": referer}, timeout=60, allow_redirects=True)
        response.raise_for_status()
        if "text/html" in response.headers.get("Content-Type", "").lower() and response.content[:4] != b"%PDF":
            raise RuntimeError("La URL devolvio HTML, no un archivo descargable.")
        target.write_bytes(response.content)
        return _register_document(
            db,
            opportunity,
            title=title,
            source_url=url,
            local_path=str(target),
            filename=target.name,
            status="downloaded",
        )
    except Exception as exc:
        return _register_document(
            db,
            opportunity,
            title=title,
            source_url=url,
            filename=filename,
            status="error",
            error_message=f"{type(exc).__name__}: {exc}",
        )


def _candidate_documents(driver, base_url: str) -> list[dict]:
    return driver.execute_script(
        """
        const out = [];
        function clean(s){return (s||'').replace(/\\s+/g,' ').trim();}
        function rowText(el){
            let p = el;
            for(let i=0; i<8 && p; i++, p=p.parentElement){
                if((p.tagName||'').toLowerCase()==='tr') return clean(p.innerText);
            }
            return clean(el.innerText || el.title || el.alt || '');
        }
        const els = Array.from(document.querySelectorAll('a,img,button,span'));
        for(const el of els){
            const href = el.getAttribute('href') || '';
            const onclick = el.getAttribute('onclick') || '';
            const src = el.getAttribute('src') || '';
            const title = rowText(el);
            const merged = (href + ' ' + onclick + ' ' + src + ' ' + title).toLowerCase();
            if(!(merged.includes('pdf') || merged.includes('zip') || merged.includes('descarga') || merged.includes('document'))) continue;
            out.push({href, onclick, src, title, outer:(el.outerHTML||'').slice(0,500)});
        }
        return out.slice(0, 20);
        """
    ) or []


def _open_document_sections(driver) -> None:
    xpath = (
        "//img[contains(translate(@src,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'ver-documento-por-etapa')]/parent::a"
        " | //a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'ver documentos del procedimiento')]"
    )
    elements = driver.find_elements(By.XPATH, xpath)[:2]
    for element in elements:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.4)
            driver.execute_script("arguments[0].click();", element)
            time.sleep(3)
        except Exception:
            continue


def _document_page_has_no_data(driver) -> bool:
    text = _clean(driver.execute_script("return document.body ? document.body.innerText : ''") or "").lower()
    return "lista de documentos" in text and "no se encontraron datos" in text


def _finished_downloads(target_dir: Path, before: set[str]) -> list[Path]:
    files = []
    for path in target_dir.glob("*"):
        suffix = path.suffix.lower()
        if not path.is_file() or path.name in before:
            continue
        if path.name.startswith(".org.chromium") or path.name.startswith(".com.google") or suffix in [".crdownload", ".tmp"]:
            continue
        if suffix and suffix not in [".pdf", ".zip", ".rar", ".7z", ".doc", ".docx", ".xls", ".xlsx"]:
            continue
        files.append(path)
    return files


def _download_action_candidates(driver) -> list[dict]:
    return driver.execute_script(
        r"""
        function clean(s){return (s||'').replace(/\s+/g,' ').trim();}
        const anchors = Array.from(document.querySelectorAll("a[onclick*='descargaDocGeneral']"));
        return anchors.map((el, index) => {
            let p = el;
            let title = "";
            for(let i=0; i<8 && p; i++, p=p.parentElement){
                if((p.tagName||'').toLowerCase()==='tr'){
                    title = clean(p.innerText);
                    break;
                }
            }
            return {
                id: el.id || "",
                index,
                title: title || clean(el.innerText || el.title || "Documento SEACE"),
                onclick: el.getAttribute("onclick") || ""
            };
        });
        """
    ) or []


def _find_download_action(driver, candidate: dict):
    element_id = candidate.get("id") or ""
    if element_id:
        try:
            return driver.find_element(By.ID, element_id)
        except Exception:
            pass
    elements = driver.find_elements(By.XPATH, "//*[contains(translate(@onclick,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'descargadocgeneral')]")
    index = int(candidate.get("index") or 0)
    if 0 <= index < len(elements):
        return elements[index]
    return None


def _click_download_candidates(db: Session, driver, opportunity: Opportunity, target_dir: Path) -> list[Document]:
    docs: list[Document] = []
    action_candidates = _download_action_candidates(driver)
    if action_candidates:
        for index, candidate in enumerate(action_candidates, start=1):
            element = _find_download_action(driver, candidate)
            if element is None:
                continue
            before = {p.name for p in target_dir.glob("*")}
            title = _clean(candidate.get("title") or "") or f"Documento SEACE {index}"
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.3)
                try:
                    ActionChains(driver).move_to_element(element).pause(0.1).click(element).perform()
                except Exception:
                    driver.execute_script("arguments[0].click();", element)
                deadline = time.time() + 45
                new_files: list[Path] = []
                while time.time() < deadline:
                    new_files = _finished_downloads(target_dir, before)
                    if new_files:
                        break
                    time.sleep(0.8)
                for path in new_files:
                    docs.append(
                        _register_local_download(
                            db,
                            opportunity,
                            path,
                            title,
                            source_url=f"{driver.current_url}#{path.name}",
                        )
                    )
            except Exception as exc:
                docs.append(
                    _register_document(
                        db,
                        opportunity,
                        title=title,
                        source_url=f"{opportunity.detail_url}#download-action-{index}",
                        status="error",
                        error_message=f"{type(exc).__name__}: {exc}",
                    )
                )
        return docs

    xpath = (
        "//*[contains(translate(@onclick,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'descargadocgeneral') "
        "or contains(translate(@onclick,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'descarga') "
        "or contains(translate(@onclick,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'document') "
        "or contains(translate(@src,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'pdf') "
        "or contains(translate(@src,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'zip') "
        "or contains(translate(@title,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'pdf') "
        "or contains(translate(@title,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'zip') "
        "or contains(translate(@alt,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'pdf') "
        "or contains(translate(@alt,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'zip')]"
    )
    elements = driver.find_elements(By.XPATH, xpath)[:20]
    for index, element in enumerate(elements, start=1):
        before = {p.name for p in target_dir.glob("*")}
        title = _clean(driver.execute_script(
            """
            const el = arguments[0];
            let p = el;
            for(let i=0; i<8 && p; i++, p=p.parentElement){
                if((p.tagName||'').toLowerCase()==='tr') return (p.innerText||'').replace(/\\s+/g,' ').trim();
            }
            return (el.innerText || el.title || el.alt || 'Documento SEACE').replace(/\\s+/g,' ').trim();
            """,
            element,
        )) or f"Documento SEACE {index}"
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", element)
            deadline = time.time() + 15
            new_files: list[Path] = []
            while time.time() < deadline:
                new_files = _finished_downloads(target_dir, before)
                if new_files:
                    break
                time.sleep(0.8)
            for path in new_files:
                docs.append(
                    _register_local_download(
                        db,
                        opportunity,
                        path,
                        title,
                        source_url=f"{driver.current_url}#{path.name}",
                    )
                )
        except Exception as exc:
            docs.append(
                _register_document(
                    db,
                    opportunity,
                    title=title,
                    source_url=f"{opportunity.detail_url}#click-{index}",
                    status="error",
                    error_message=f"{type(exc).__name__}: {exc}",
                )
            )
    return docs


def discover_documents_for_opportunity(db: Session, opportunity_id: int) -> list[Document]:
    opportunity = db.get(Opportunity, opportunity_id)
    if not opportunity:
        raise ValueError("Opportunity not found")
    if not opportunity.detail_url:
        return [
            _register_document(
                db,
                opportunity,
                title="Sin URL de detalle",
                status="error",
                error_message="La oportunidad no tiene url_detalle.",
            )
        ]

    target_dir = (DOCUMENT_ROOT / str(opportunity.id)).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    options = Options()
    for opt in [
        "--headless=new",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-notifications",
        "--disable-popup-blocking",
        "--ignore-certificate-errors",
    ]:
        options.add_argument(opt)
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": str(target_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True,
            "safebrowsing.enabled": True,
        },
    )
    driver = None
    docs: list[Document] = []
    try:
        driver = webdriver.Chrome(options=options)
        driver.get(opportunity.detail_url)
        time.sleep(4)
        if not _page_has_process_data(driver, opportunity):
            _open_detail_from_search(driver, opportunity)
        _open_document_sections(driver)
        candidates = _candidate_documents(driver, opportunity.detail_url)
        cookies = driver.get_cookies()
        for candidate in candidates:
            href = candidate.get("href") or ""
            title = candidate.get("title") or candidate.get("src") or "Documento SEACE"
            if href and href != "#":
                full_url = urljoin(opportunity.detail_url, href)
                docs.append(_download_direct(db, opportunity, full_url, title, cookies=cookies, referer=opportunity.detail_url))
        if not docs:
            docs.extend(_click_download_candidates(db, driver, opportunity, target_dir))
        if not docs:
            if _document_page_has_no_data(driver):
                message = "SEACE devolvio la lista de documentos sin datos descargables para esta ficha."
            else:
                message = "La ficha contiene iconos/documentos, pero no se encontro href descargable directo. Se requiere automatizar click especifico del portal SEACE."
            docs.append(
                _register_document(
                    db,
                    opportunity,
                    title="Documentos detectados sin enlace directo",
                    status="error",
                    error_message=message,
                )
            )
        return docs
    except Exception as exc:
        return [
            _register_document(
                db,
                opportunity,
                title="Error descubriendo documentos",
                status="error",
                error_message=f"{type(exc).__name__}: {exc}",
            )
        ]
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
