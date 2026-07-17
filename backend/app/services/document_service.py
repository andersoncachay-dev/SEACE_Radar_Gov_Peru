from __future__ import annotations

import mimetypes
import json
import re
import time
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Document, Opportunity, OpportunitySnapshot
from src.proxy_utils import requests_proxies

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


def _probe_document_extension(url: str) -> str:
    """OCDS document URLs (SdescargarArchivoAlfresco?fileCode=...) carry no
    filename/extension of their own, so the type badge would otherwise always
    fall back to "PDF" regardless of the real file. A lightweight HEAD (or,
    failing that, a streamed GET closed immediately) reads Content-Disposition
    / Content-Type to recover the real extension without downloading the
    whole file."""
    headers = {"User-Agent": "GovRadar CRM/1.0"}
    try:
        response = requests.head(url, timeout=10, allow_redirects=True, headers=headers, proxies=requests_proxies())
        if response.status_code >= 400 or not response.headers.get("Content-Type"):
            response = requests.get(url, timeout=15, stream=True, allow_redirects=True, headers=headers, proxies=requests_proxies())
            response.close()
        disposition = response.headers.get("Content-Disposition", "")
        match = re.search(r"filename\*?=(?:UTF-8''|\"?)([^\";]+)", disposition, re.I)
        if match:
            suffix = Path(unquote(match.group(1))).suffix.lower().replace(".", "")
            if suffix:
                return suffix
        content_type = (response.headers.get("Content-Type", "") or "").split(";")[0].strip()
        guessed = mimetypes.guess_extension(content_type) if content_type else None
        if guessed:
            return guessed.lower().replace(".", "")
    except Exception:
        pass
    return ""


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
    try:
        session = requests.Session()
        if cookies:
            for cookie in cookies:
                session.cookies.set(cookie.get("name"), cookie.get("value"), domain=cookie.get("domain"))
        response = session.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": referer}, timeout=60, allow_redirects=True)
        response.raise_for_status()
        if "text/html" in response.headers.get("Content-Type", "").lower() and response.content[:4] != b"%PDF":
            raise RuntimeError("La URL devolvio HTML, no un archivo descargable.")
        disposition = response.headers.get("Content-Disposition", "")
        disposition_match = re.search(r"filename\*?=(?:UTF-8''|\"?)([^\";]+)", disposition, re.I)
        if disposition_match:
            filename = _safe_filename(unquote(disposition_match.group(1)))
        target = target_dir / filename
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


def _click_chile_attachments(driver) -> bool:
    selectors = [
        (By.ID, "imgAdjuntos"),
        (By.XPATH, "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'ver adjuntos')]"),
        (By.XPATH, "//*[contains(translate(@title,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'adjunto') or contains(translate(@alt,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'adjunto')]"),
    ]
    for by, selector in selectors:
        try:
            elements = driver.find_elements(by, selector)
        except Exception:
            continue
        for element in elements:
            try:
                if not element.is_displayed():
                    continue
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", element)
                return True
            except Exception:
                continue
    return False


def _chile_protected_attachments_url(driver) -> str:
    try:
        onclick = driver.find_element(By.ID, "imgAdjuntos").get_attribute("onclick") or ""
    except Exception:
        return ""
    match = re.search(r"open\('([^']+ViewAttachment\.aspx\?enc=[^']+)'", onclick, re.I)
    if not match:
        return ""
    return urljoin(driver.current_url, match.group(1))


def _chile_direct_attachment_links(driver) -> list[dict]:
    return driver.execute_script(
        r"""
        function clean(s){return (s||'').replace(/\s+/g,' ').trim();}
        const out = [];
        for(const el of Array.from(document.querySelectorAll("a,input,img,button"))){
            const href = el.href || el.getAttribute('href') || '';
            if(!href.includes('Attachment/VerAntecedentes')) continue;
            let p = el;
            let title = clean(el.innerText || el.value || el.title || el.alt || '');
            for(let i=0; i<8 && p; i++, p=p.parentElement){
                if((p.tagName||'').toLowerCase()==='tr'){
                    title = clean(p.innerText) || title;
                    break;
                }
            }
            out.push({href, title: title || 'Documento Mercado Publico'});
        }
        return out.slice(0, 20);
        """
    ) or []


def _find_chile_direct_attachment(driver, index: int):
    return driver.execute_script(
        """
        const elements = Array.from(document.querySelectorAll('a,input,img,button'))
            .filter(el => String(el.href || el.getAttribute('href') || '').includes('Attachment/VerAntecedentes'));
        const el = elements[arguments[0]] || null;
        return el ? (el.closest('a') || el) : null;
        """,
        index,
    )


def _filename_from_disposition(disposition: str, fallback: str) -> str:
    disposition_match = re.search(r"filename\*?=(?:UTF-8''|\"?)([^\";]+)", disposition or "", re.I)
    if disposition_match:
        return _safe_filename(unquote(disposition_match.group(1)))
    return _safe_filename(fallback)


def _download_chile_attachment_page(
    db: Session,
    opportunity: Opportunity,
    *,
    session: requests.Session,
    url: str,
    title: str,
    target_dir: Path,
    referer: str,
) -> list[Document]:
    docs: list[Document] = []
    try:
        response = session.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": referer}, timeout=45)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        image_buttons = [item for item in soup.find_all("input") if (item.get("type") or "").lower() == "image" and item.get("name")]
        hidden_payload = {
            item.get("name"): item.get("value") or ""
            for item in soup.find_all("input")
            if item.get("name") and (item.get("type") or "").lower() != "image"
        }
        for index, button in enumerate(image_buttons, start=1):
            button_name = button.get("name") or ""
            payload = dict(hidden_payload)
            payload[f"{button_name}.x"] = "10"
            payload[f"{button_name}.y"] = "10"
            row_title = _clean(button.find_parent("tr").get_text(" ", strip=True) if button.find_parent("tr") else "") or title
            download = session.post(
                url,
                data=payload,
                headers={"User-Agent": "Mozilla/5.0", "Referer": url},
                timeout=60,
                allow_redirects=True,
            )
            download.raise_for_status()
            content_type = download.headers.get("Content-Type", "").lower()
            if "text/html" in content_type and download.content[:4] != b"%PDF":
                docs.append(
                    _register_document(
                        db,
                        opportunity,
                        title=row_title,
                        source_url=f"{url}#{button_name}",
                        status="error",
                        error_message="Mercado Publico devolvio HTML al intentar descargar el anexo.",
                    )
                )
                continue
            filename = _filename_from_disposition(download.headers.get("Content-Disposition", ""), row_title)
            target = target_dir / filename
            target.write_bytes(download.content)
            docs.append(
                _register_document(
                    db,
                    opportunity,
                    title=row_title,
                    source_url=f"{url}#{button_name}",
                    local_path=str(target),
                    filename=target.name,
                    status="downloaded",
                )
            )
        return docs
    except Exception as exc:
        return [
            _register_document(
                db,
                opportunity,
                title=title,
                source_url=url,
                status="error",
                error_message=f"{type(exc).__name__}: {exc}",
            )
        ]


def _click_chile_direct_links(db: Session, driver, opportunity: Opportunity, target_dir: Path) -> list[Document]:
    docs: list[Document] = []
    candidates = _chile_direct_attachment_links(driver)
    for index, candidate in enumerate(candidates):
        element = _find_chile_direct_attachment(driver, index)
        if element is None:
            continue
        title = _clean(candidate.get("title") or "") or f"Documento Mercado Publico {index + 1}"
        before_files = {p.name for p in target_dir.glob("*")}
        before_handles = set(driver.window_handles)
        current_handle = driver.current_window_handle
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.3)
            try:
                ActionChains(driver).move_to_element(element).pause(0.1).click(element).perform()
            except Exception:
                driver.execute_script("arguments[0].click();", element)
            deadline = time.time() + 12
            new_files: list[Path] = []
            while time.time() < deadline:
                new_files = _finished_downloads(target_dir, before_files)
                if new_files:
                    break
                opened = list(set(driver.window_handles) - before_handles)
                if opened:
                    driver.switch_to.window(opened[-1])
                    time.sleep(2)
                    new_files = _finished_downloads(target_dir, before_files)
                    if new_files:
                        break
                    if driver.current_url and not driver.current_url.startswith("data:"):
                        docs.append(_download_direct(db, opportunity, driver.current_url, title, cookies=driver.get_cookies(), referer=opportunity.detail_url))
                    driver.close()
                    driver.switch_to.window(current_handle)
                    break
                time.sleep(0.8)
            if not new_files and driver.current_window_handle == current_handle and driver.current_url != opportunity.detail_url:
                docs.append(_download_direct(db, opportunity, driver.current_url, title, cookies=driver.get_cookies(), referer=opportunity.detail_url))
                driver.get(opportunity.detail_url)
                time.sleep(2)
            for path in new_files:
                docs.append(_register_local_download(db, opportunity, path, title, source_url=f"{opportunity.detail_url}#{path.name}"))
        except Exception as exc:
            docs.append(
                _register_document(
                    db,
                    opportunity,
                    title=title,
                    source_url=f"{opportunity.detail_url}#mercado-publico-directo-{index + 1}",
                    status="error",
                    error_message=f"{type(exc).__name__}: {exc}",
                )
            )
    return docs


def _chile_attachment_actions(driver) -> list[dict]:
    return driver.execute_script(
        r"""
        function clean(s){return (s||'').replace(/\s+/g,' ').trim();}
        const rows = Array.from(document.querySelectorAll('tr'));
        const out = [];
        for(const tr of rows){
            const text = clean(tr.innerText || '');
            const normalized = text.toLowerCase();
            if(!text || !(normalized.includes('base') || normalized.includes('.pdf') || normalized.includes('.doc') || normalized.includes('anexo'))) continue;
            const actions = Array.from(tr.querySelectorAll('a,button,input,img'));
            let action = null;
            for(const el of actions.reverse()){
                const merged = clean((el.innerText||'')+' '+(el.value||'')+' '+(el.title||'')+' '+(el.alt||'')+' '+(el.href||'')+' '+(el.getAttribute('onclick')||'')).toLowerCase();
                if(merged.includes('ver') || merged.includes('download') || merged.includes('attachment') || merged.includes('adjunto') || merged.includes('lupa')){
                    action = el;
                    break;
                }
            }
            if(action){
                out.push({
                    id: action.id || '',
                    index: out.length,
                    title: text,
                    href: action.getAttribute('href') || '',
                    onclick: action.getAttribute('onclick') || ''
                });
            }
        }
        return out.slice(0, 12);
        """
    ) or []


def _find_chile_attachment_action(driver, candidate: dict):
    element_id = candidate.get("id") or ""
    if element_id:
        try:
            return driver.find_element(By.ID, element_id)
        except Exception:
            pass
    actions = driver.execute_script(
        r"""
        function clean(s){return (s||'').replace(/\s+/g,' ').trim();}
        const out = [];
        for(const tr of Array.from(document.querySelectorAll('tr'))){
            const text = clean(tr.innerText || '').toLowerCase();
            if(!text || !(text.includes('base') || text.includes('.pdf') || text.includes('.doc') || text.includes('anexo'))) continue;
            const candidates = Array.from(tr.querySelectorAll('a,button,input,img'));
            for(const el of candidates.reverse()){
                const merged = clean((el.innerText||'')+' '+(el.value||'')+' '+(el.title||'')+' '+(el.alt||'')+' '+(el.href||'')+' '+(el.getAttribute('onclick')||'')).toLowerCase();
                if(merged.includes('ver') || merged.includes('download') || merged.includes('attachment') || merged.includes('adjunto') || merged.includes('lupa')){
                    out.push(el);
                    break;
                }
            }
        }
        return out;
        """
    ) or []
    index = int(candidate.get("index") or 0)
    return actions[index] if 0 <= index < len(actions) else None


def _click_chile_ficha_pdf(db: Session, driver, opportunity: Opportunity, target_dir: Path) -> list[Document]:
    nomen = _nomenclature(opportunity)
    existing_pdf = target_dir / f"PDF{nomen}.pdf" if nomen else None
    if existing_pdf and existing_pdf.exists() and existing_pdf.stat().st_size > 0:
        return [
            _register_local_download(
                db,
                opportunity,
                existing_pdf,
                "Ficha Mercado Publico",
                source_url=f"{opportunity.detail_url}#descargar_pdf:{existing_pdf.name}",
            )
        ]
    candidates = [
        ("descargar_pdf", "Ficha Mercado Publico"),
        ("imgPDF", "Ficha Mercado Publico"),
    ]
    docs: list[Document] = []
    for element_id, title in candidates:
        try:
            element = driver.find_element(By.ID, element_id)
        except Exception:
            continue
        before_files = {p.name for p in target_dir.glob("*")}
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.2)
            try:
                ActionChains(driver).move_to_element(element).pause(0.1).click(element).perform()
            except Exception:
                driver.execute_script("arguments[0].click();", element)
            deadline = time.time() + 25
            new_files: list[Path] = []
            while time.time() < deadline:
                new_files = _finished_downloads(target_dir, before_files)
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
                        source_url=f"{opportunity.detail_url}#{element_id}:{path.name}",
                    )
                )
            if docs:
                return docs
        except Exception as exc:
            try:
                driver.switch_to.alert.accept()
            except Exception:
                pass
            docs.append(
                _register_document(
                    db,
                    opportunity,
                    title=title,
                    source_url=f"{opportunity.detail_url}#{element_id}",
                    status="error",
                    error_message=f"{type(exc).__name__}: {exc}",
                )
            )
    return docs


def _unique_documents(docs: list[Document]) -> list[Document]:
    unique: list[Document] = []
    seen: set[int] = set()
    for doc in docs:
        if doc.id in seen:
            continue
        seen.add(doc.id)
        unique.append(doc)
    return unique


def _ordered_documents(docs: list[Document]) -> list[Document]:
    unique = _unique_documents(docs)
    return sorted(
        unique,
        key=lambda doc: (
            0 if (doc.title or "").lower().startswith("ficha mercado publico") else 1,
            0 if doc.status == "downloaded" else 1,
            (doc.title or doc.filename or "").lower(),
        ),
    )


def _is_chile_protected_route(doc: Document) -> bool:
    return (doc.title or "").lower().startswith("ruta protegida")


def _visible_chile_documents(docs: list[Document]) -> list[Document]:
    visible = [doc for doc in docs if doc.status == "downloaded" or _is_chile_protected_route(doc)]
    return _ordered_documents(visible)


def _register_chile_protected_route(db: Session, opportunity: Opportunity, protected_url: str) -> Document | None:
    if not protected_url:
        return None
    return _register_document(
        db,
        opportunity,
        title="Ruta Protegida Mercado Publico",
        source_url=protected_url,
        status="error",
        error_message=f"Ruta Protegida: Descargar desde el link: {protected_url}",
    )


def _discover_chile_documents(db: Session, opportunity: Opportunity, driver, target_dir: Path) -> list[Document]:
    docs: list[Document] = []
    driver.get(opportunity.detail_url)
    time.sleep(4)
    protected_url = _chile_protected_attachments_url(driver)
    docs.extend(_click_chile_ficha_pdf(db, driver, opportunity, target_dir))
    driver.get(opportunity.detail_url)
    time.sleep(2)
    protected_url = protected_url or _chile_protected_attachments_url(driver)
    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie.get("name"), cookie.get("value"), domain=cookie.get("domain"))
    for candidate in _chile_direct_attachment_links(driver):
        href = _clean(candidate.get("href") or "")
        if not href:
            continue
        docs.extend(
            _download_chile_attachment_page(
                db,
                opportunity,
                session=session,
                url=urljoin(driver.current_url, href),
                title=_clean(candidate.get("title") or "Documento Mercado Publico"),
                target_dir=target_dir,
                referer=driver.current_url,
            )
        )
    downloaded = [doc for doc in docs if doc.status == "downloaded"]
    if len(downloaded) <= 1:
        docs.extend(_click_chile_direct_links(db, driver, opportunity, target_dir))
    driver.get(opportunity.detail_url)
    time.sleep(2)
    before_handles = set(driver.window_handles)
    if not _click_chile_attachments(driver):
        protected_doc = _register_chile_protected_route(db, opportunity, protected_url)
        if protected_doc:
            docs.append(protected_doc)
        visible = _visible_chile_documents(docs)
        return visible if visible else [
            _register_document(
                db,
                opportunity,
                title="Sin acceso a adjuntos Mercado Publico",
                status="error",
                error_message="No se encontro la accion Ver adjuntos en la ficha de Mercado Publico.",
            )
        ]
    time.sleep(2)
    new_handles = list(set(driver.window_handles) - before_handles)
    if new_handles:
        driver.switch_to.window(new_handles[-1])
        time.sleep(2)
    actions = _chile_attachment_actions(driver)
    cookies = driver.get_cookies()
    if not actions and "403" in (driver.current_url or ""):
        protected_doc = _register_chile_protected_route(db, opportunity, protected_url or opportunity.detail_url)
        if protected_doc:
            docs.append(protected_doc)
    for index, candidate in enumerate(actions, start=1):
        title = _clean(candidate.get("title") or "") or f"Documento Mercado Publico {index}"
        href = _clean(candidate.get("href") or "")
        if href and not href.lower().startswith("javascript"):
            docs.append(_download_direct(db, opportunity, urljoin(driver.current_url, href), title, cookies=cookies, referer=driver.current_url))
            continue
        element = _find_chile_attachment_action(driver, candidate)
        if element is None:
            continue
        before_files = {p.name for p in target_dir.glob("*")}
        before_click_handles = set(driver.window_handles)
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.2)
            attachment_handle = driver.current_window_handle
            try:
                ActionChains(driver).move_to_element(element).pause(0.1).click(element).perform()
            except Exception:
                driver.execute_script("arguments[0].click();", element)
            deadline = time.time() + 45
            new_files: list[Path] = []
            while time.time() < deadline:
                new_files = _finished_downloads(target_dir, before_files)
                if new_files:
                    break
                opened = list(set(driver.window_handles) - before_click_handles)
                if opened:
                    driver.switch_to.window(opened[-1])
                    time.sleep(1)
                    if driver.current_url and not driver.current_url.startswith("data:"):
                        docs.append(_download_direct(db, opportunity, driver.current_url, title, cookies=driver.get_cookies(), referer=opportunity.detail_url))
                    driver.close()
                    driver.switch_to.window(attachment_handle)
                    break
                time.sleep(0.8)
            for path in new_files:
                docs.append(_register_local_download(db, opportunity, path, title, source_url=f"{driver.current_url}#{path.name}"))
        except Exception as exc:
            docs.append(
                _register_document(
                    db,
                    opportunity,
                    title=title,
                    source_url=f"{opportunity.detail_url}#mercado-publico-adjunto-{index}",
                    status="error",
                    error_message=f"{type(exc).__name__}: {exc}",
                )
            )
    if protected_url and not any(_is_chile_protected_route(doc) for doc in docs):
        protected_doc = _register_chile_protected_route(db, opportunity, protected_url)
        if protected_doc:
            docs.append(protected_doc)
    visible = _visible_chile_documents(docs)
    if visible:
        return visible
    return [
        _register_document(
            db,
            opportunity,
            title="Ruta Protegida Mercado Publico",
            source_url=protected_url or opportunity.detail_url,
            status="error",
            error_message=f"Ruta Protegida: Descargar desde el link: {protected_url or opportunity.detail_url}",
        )
    ]


def discover_documents_for_opportunity(db: Session, opportunity_id: int) -> list[Document]:
    opportunity = db.get(Opportunity, opportunity_id)
    if not opportunity:
        raise ValueError("Opportunity not found")
    if opportunity.source == "oece_ocds_api":
        snapshot = db.scalar(
            select(OpportunitySnapshot)
            .where(OpportunitySnapshot.opportunity_id == opportunity.id)
            .order_by(OpportunitySnapshot.id.desc())
        )
        docs_payload: list[dict] = []
        if snapshot and snapshot.raw_payload:
            try:
                raw_payload = json.loads(snapshot.raw_payload)
                raw_docs = raw_payload.get("documentos_ocds") or "[]"
                docs_payload = json.loads(raw_docs) if isinstance(raw_docs, str) else raw_docs
            except Exception:
                docs_payload = []
        if not docs_payload and opportunity.detail_url:
            try:
                response = requests.get(
                    opportunity.detail_url,
                    timeout=45,
                    headers={"User-Agent": "GovRadar CRM/1.0"},
                    proxies=requests_proxies(),
                )
                response.raise_for_status()
                payload = response.json()
                releases = payload.get("releases") or []
                release = releases[0] if releases else payload.get("compiledRelease") or payload
                tender_docs = ((release.get("tender") or {}).get("documents") or [])
                docs_payload = [
                    {
                        "title": _clean(item.get("title") or item.get("description") or "Documento OCDS"),
                        "url": _clean(item.get("url")),
                    }
                    for item in tender_docs
                    if _clean(item.get("url"))
                ]
            except Exception:
                docs_payload = []
        if not docs_payload and opportunity.requirement_pdf_url:
            docs_payload = [{"title": "Documento OCDS", "url": opportunity.requirement_pdf_url}]
        docs = []
        for item in docs_payload:
            url = _clean(item.get("url"))
            if not url:
                continue
            title = _clean(item.get("title") or "Documento OCDS")
            extension = _probe_document_extension(url)
            filename = _safe_filename(f"{title}.{extension}" if extension else title)
            docs.append(
                _register_document(
                    db,
                    opportunity,
                    title=title,
                    source_url=url,
                    filename=filename,
                    status="registered",
                )
            )
        if docs:
            return docs
        return [
            _register_document(
                db,
                opportunity,
                title="Sin documentos OCDS",
                status="error",
                error_message="La API OCDS no devolvio enlaces de documentos para esta oportunidad.",
            )
        ]
    if not opportunity.detail_url and not opportunity.source.startswith("mercado_publico"):
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
        try:
            driver.execute_cdp_cmd("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(target_dir)})
        except Exception:
            pass
        if opportunity.source.startswith("mercado_publico") and not opportunity.detail_url:
            # Older Chile opportunities were saved before url_detalle was
            # captured (bulk-Excel discovery never had a ficha link to save).
            # Reproduce the manual recovery: search Mercado Publico's
            # Busqueda Avanzada by the exact code and open its ficha live.
            from src.mercado_publico_scraper import _open_detail_by_nomenclature

            nomenclature = str(opportunity.nomenclature or "").strip()
            resolved = False
            if nomenclature:
                try:
                    resolved = _open_detail_by_nomenclature(driver, nomenclature, driver.current_window_handle)
                except Exception:
                    resolved = False
            if resolved:
                opportunity.detail_url = driver.current_url
                db.commit()
                db.refresh(opportunity)
            if not opportunity.detail_url:
                return [
                    _register_document(
                        db,
                        opportunity,
                        title="Sin URL de detalle",
                        status="error",
                        error_message="No se encontro la ficha de este proceso por numero de codigo en Mercado Publico.",
                    )
                ]

        if opportunity.source.startswith("mercado_publico"):
            return _discover_chile_documents(db, opportunity, driver, target_dir)
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
