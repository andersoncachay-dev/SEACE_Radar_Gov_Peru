from typing import Tuple, List
import time
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
import pandas as pd
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By

MENOR8_AUTH_URL = "https://prod6.seace.gob.pe/auth-proveedor/"
MENOR8_SEARCH_URL = "https://prod6.seace.gob.pe/cotizacion/contrataciones"
BASE_URL = "https://prod6.seace.gob.pe"
DOWNLOAD_DIR = Path.cwd() / "exports" / "requerimientos_menores8uit"


def _clean(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()


def _norm(v):
    return _clean(v).lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u").replace("ñ", "n")


def _dedupe_columns(df):
    try:
        return df.loc[:, ~df.columns.duplicated()].copy()
    except Exception:
        return df


def _to_dt(v):
    if not v:
        return pd.NaT
    return pd.to_datetime(v, dayfirst=True, errors="coerce")


def _dias_hasta(v):
    dt = _to_dt(v)
    if pd.isna(dt):
        return ""
    return int((dt.normalize() - pd.Timestamp.now().normalize()).days)


def _horas_hasta(v):
    dt = _to_dt(v)
    if pd.isna(dt):
        return ""
    return round((dt - pd.Timestamp.now()).total_seconds() / 3600, 2)


def _situacion_vencimiento(v):
    dt = _to_dt(v)
    if pd.isna(dt):
        return ""
    now = pd.Timestamp.now()
    if now <= dt:
        return "Vence hoy" if dt.normalize() == now.normalize() else "Vigente"
    return "Vencido hoy" if dt.normalize() == now.normalize() else "Vencido"


def _extract_datetime(text):
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2}|\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}|\d{1,2}/\d{1,2}/\d{4})", str(text or ""))
    return m.group(1) if m else ""


def _sanitize_filename(name):
    name = unquote(str(name or "")).strip()
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:180] or "requerimiento.pdf"


def _filename_from_url_or_text(url, text, codigo):
    parsed = urlparse(url or "")
    base = Path(unquote(parsed.path)).name
    if not base or "." not in base:
        base = text or f"{codigo}_requerimiento.pdf"
    if not base.lower().endswith(".pdf"):
        base = f"{base}.pdf"
    return _sanitize_filename(f"{codigo}_{base}")


def _build_detail_url(raw_href):
    href = _clean(raw_href)
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return urljoin(BASE_URL, href)
    if href.startswith("contratacion-detalle"):
        return urljoin(BASE_URL + "/cotizacion/contrataciones/", href)
    if "/contratacion-detalle/" in href:
        return urljoin(BASE_URL, href)
    return ""


def _is_search_page(driver):
    cur = driver.current_url.lower()
    return "/cotizacion/contrataciones" in cur and "auth-proveedor" not in cur and "contratacion-detalle" not in cur


def _is_terms_page(driver):
    cur = driver.current_url.lower()
    html = driver.page_source.lower()
    return "terminos-condiciones" in cur or "política de privacidad" in html or "terminos y condiciones" in html or "términos y condiciones" in html


def _wait_loader_gone(driver, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        try:
            visible = driver.execute_script("""
                const overlays = Array.from(document.querySelectorAll(
                    '.screen-loader-overlay, [role="dialog"], .cdk-overlay-backdrop, .loading, .loader'
                ));
                return overlays.some(el => {
                    const st = window.getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    return st.display !== 'none' && st.visibility !== 'hidden' && Number(st.opacity || 1) > 0 && r.width > 0 && r.height > 0;
                });
            """)
            if not visible:
                return True
        except Exception:
            return True
        time.sleep(0.4)
    return False


def _wait_for_search_page(driver, seconds, diagnostics, label="buscador"):
    end = time.time() + seconds
    while time.time() < end:
        _wait_loader_gone(driver, timeout=5)
        if _is_search_page(driver):
            diagnostics.append(f"{label}: detectado correctamente.")
            return True
        time.sleep(1)
    diagnostics.append(f"{label}: no detectado dentro del tiempo configurado.")
    return False


def _safe_click(driver, el):
    if el is None:
        return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.2)
        ActionChains(driver).move_to_element(el).pause(0.1).click(el).perform()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            return False


def _accept_terms_if_present(driver, diagnostics):
    if not _is_terms_page(driver):
        return False
    diagnostics.append("Términos y condiciones detectados.")
    try:
        for ch in driver.find_elements(By.XPATH, "//input[@type='checkbox']"):
            try:
                if not ch.is_selected():
                    _safe_click(driver, ch)
                    break
            except Exception:
                pass
        time.sleep(0.5)
        for btn in driver.find_elements(By.XPATH, "//*[self::button or self::a or self::span or self::div][contains(normalize-space(.),'Acepto')]"):
            if "No Acepto" in _clean(btn.text):
                continue
            if _safe_click(driver, btn):
                diagnostics.append("Términos aceptados automáticamente.")
                time.sleep(3)
                return True
    except Exception as e:
        diagnostics.append(f"No se pudo aceptar términos: {type(e).__name__} - {e}")
    return False


def _wait_manual_login(driver, auth_url, seconds, diagnostics):
    driver.get(auth_url)
    diagnostics.append("Login manual: Chrome queda abierto para ingresar credenciales RNP.")
    diagnostics.append(f"Login manual: esperando hasta {seconds} segundos para llegar al buscador.")
    end = time.time() + seconds
    while time.time() < end:
        if _is_search_page(driver):
            diagnostics.append("Login manual: buscador detectado correctamente.")
            return True
        if _is_terms_page(driver):
            _accept_terms_if_present(driver, diagnostics)
            if _is_search_page(driver):
                diagnostics.append("Login manual: buscador detectado después de aceptar términos.")
                return True
        time.sleep(2)
    diagnostics.append("Login manual: no se detectó el buscador dentro del tiempo configurado.")
    return False


def _find_search_input(driver):
    js = """
    const inputs = Array.from(document.querySelectorAll('input'));
    for (const i of inputs) {
      const txt = ((i.placeholder||'')+' '+(i.ariaLabel||'')+' '+(i.name||'')+' '+(i.id||'')).toLowerCase();
      if (txt.includes('buscar') || txt.includes('descrip') || txt.includes('requerimiento') || txt.includes('numero') || txt.includes('entidad')) return i;
    }
    return inputs.length ? inputs[0] : null;
    """
    return driver.execute_script(js)


def _click_search(driver):
    js = """
    const candidates = Array.from(document.querySelectorAll('button,a,span,img'));
    function n(s){return (s||'').toLowerCase();}
    for (const el of candidates) {
      const txt = n(el.innerText)+' '+n(el.title)+' '+n(el.alt)+' '+n(el.className);
      if (txt.includes('buscar') || txt.includes('search') || txt.includes('lupa') || txt.includes('fa-search')) return el;
    }
    return null;
    """
    return _safe_click(driver, driver.execute_script(js))


def _force_keyword_search(driver, keyword, diagnostics):
    _wait_loader_gone(driver, timeout=30)
    inp = _find_search_input(driver)
    if not inp:
        diagnostics.append("No se encontró input de búsqueda para reaplicar filtro.")
        return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inp)
        _wait_loader_gone(driver, timeout=30)
        driver.execute_script("""
            const i = arguments[0];
            const value = arguments[1];
            i.focus();
            i.value = '';
            i.dispatchEvent(new Event('input', {bubbles:true}));
            i.dispatchEvent(new Event('change', {bubbles:true}));
            i.value = value;
            i.dispatchEvent(new Event('input', {bubbles:true}));
            i.dispatchEvent(new Event('change', {bubbles:true}));
        """, inp, keyword)
        time.sleep(0.3)
        clicked = _click_search(driver)
        if not clicked:
            try:
                inp.send_keys(Keys.ENTER)
            except Exception:
                driver.execute_script("""
                    const i = arguments[0];
                    i.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', bubbles:true}));
                    i.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', code:'Enter', bubbles:true}));
                """, inp)
        diagnostics.append(f"Filtro reaplicado: {keyword}")
        return True
    except Exception as e:
        diagnostics.append(f"Error reaplicando filtro {keyword}: {type(e).__name__} - {e}")
        return False


def _get_registered_count(driver):
    try:
        txt = _clean(BeautifulSoup(driver.page_source, "html.parser").get_text(" ", strip=True))
        m = re.search(r"Contrataciones registradas\s*\((\d+)\)", txt, re.I)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None


def _get_card_texts(driver, limit=10):
    try:
        return driver.execute_script("""
            const blocks = Array.from(document.querySelectorAll('div,section,article,li,tr'))
                .filter(el => (el.innerText || '').includes('CM-') && ((el.innerText || '').includes('Cotizaciones:') || (el.innerText || '').includes('Fecha de publicación')));
            blocks.sort((a,b) => (a.innerText||'').length - (b.innerText||'').length);
            const seen = new Set();
            const out = [];
            for (const el of blocks){
                const t = (el.innerText || '').replace(/\s+/g,' ').trim();
                const m = t.match(/CM-[A-Z0-9\-\/]+/);
                if (!m) continue;
                if (seen.has(m[0])) continue;
                seen.add(m[0]);
                out.push(t);
                if (out.length >= arguments[0]) break;
            }
            return out;
        """, limit) or []
    except Exception:
        return []


def _cards_contain_keyword(driver, keyword, min_hits=1):
    if not keyword:
        return True
    cards = _get_card_texts(driver, limit=10)
    if not cards:
        return False
    kw = keyword.lower()
    return sum(1 for c in cards if kw in c.lower()) >= min_hits


def _filter_is_effective(driver, keyword, max_allowed_total=1000):
    try:
        txt = _clean(BeautifulSoup(driver.page_source, "html.parser").get_text(" ", strip=True))
        total = _get_registered_count(driver)
        if total is not None and total > max_allowed_total:
            return False
        if "CM-" not in txt:
            return False
        if keyword and not _cards_contain_keyword(driver, keyword, min_hits=1):
            return False
        return True
    except Exception:
        return False


def _wait_filtered_results_loaded(driver, keyword, seconds, diagnostics, max_allowed_total=1000):
    end = time.time() + seconds
    last_total = None
    while time.time() < end:
        _wait_loader_gone(driver, timeout=10)
        txt = _clean(BeautifulSoup(driver.page_source, "html.parser").get_text(" ", strip=True))
        total = _get_registered_count(driver)
        last_total = total if total is not None else last_total
        if "Contrataciones registradas" in txt and "CM-" in txt:
            if _filter_is_effective(driver, keyword, max_allowed_total=max_allowed_total):
                diagnostics.append(f"Resultados filtrados correctamente para '{keyword}'. Total visible={total}")
                return True
            if total is not None and total > max_allowed_total:
                diagnostics.append(f"Filtro perdido detectado. Total visible={total}. Reaplicando '{keyword}'.")
                _force_keyword_search(driver, keyword, diagnostics)
        time.sleep(1)
    diagnostics.append(f"No se confirmaron resultados filtrados para '{keyword}' dentro del tiempo. Último total={last_total}")
    return False


def _find_requirement_href_and_text(tag):
    for a in tag.find_all("a"):
        href = a.get("href") or ""
        txt = _clean(a.get_text(" ", strip=True))
        ntxt = _norm(txt)
        if "descargar" in ntxt or "requerimiento" in ntxt or "tdr" in ntxt or "pdf" in href.lower():
            return urljoin(BASE_URL, href), txt
    return "", ""


def _find_detail_href_in_tag(tag):
    for el in tag.find_all(["a", "button", "span", "div"]):
        attrs = []
        for a in ["href", "routerlink", "ng-reflect-router-link", "data-url", "data-href"]:
            v = el.get(a)
            if v:
                attrs.append(v)
        txt = _clean(el.get_text(" ", strip=True))
        ntxt = _norm(" ".join(attrs) + " " + txt)
        if "contratacion-detalle" in ntxt or "ver detalle" in ntxt:
            for v in attrs:
                if "contratacion-detalle" in v:
                    return _build_detail_url(v)
    return ""


def _parse_list_cards(html, limit=50):
    soup = BeautifulSoup(html, "html.parser")
    rows, seen = [], set()
    for tag in soup.find_all(["div", "section", "article", "li"]):
        t = _clean(tag.get_text(" ", strip=True))
        if "CM-" not in t or not any(x in t for x in ["Cotizaciones:", "Fecha de publicación", "Ver detalle", "Descargar requerimiento"]):
            continue
        m = re.search(r"(?:\d+\.\s*)?(CM-[A-Z0-9\-\/]+)", t)
        if not m:
            continue
        codigo = m.group(1)
        if codigo in seen:
            continue
        seen.add(codigo)
        estado = "Vigente" if "Vigente" in t else ("En Evaluación" if "En Evaluación" in t or "En Evaluacion" in t else ("Culminado" if "Culminado" in t else ""))
        after = re.sub(r"^(Vigente|En Evaluación|En Evaluacion|Culminado)\s+", "", t.split(codigo, 1)[-1].strip()).strip()
        tipo = desc = entidad = ""
        mo = re.search(r"(Servicio|Bien|Obra|Consultoría de Obra|Consultoria de Obra)\s*:\s*(.*?)(?:Cotizaciones:|Fecha de publicación:|Descargar requerimiento|Ver detalle|Consultas|$)", after, re.I)
        if mo:
            tipo, desc = _clean(mo.group(1)), _clean(mo.group(2))
            entidad = _clean(after.split(mo.group(0), 1)[0])
        else:
            entidad = _clean(after[:180])
        cot_ini = cot_fin = pub = ""
        mc = re.search(r"Cotizaciones:\s*(.*?)\s*-\s*(.*?)(?:Fecha de publicación:|Descargar requerimiento|Ver detalle|Consultas|$)", t, re.I)
        if mc:
            cot_ini, cot_fin = _extract_datetime(mc.group(1)), _extract_datetime(mc.group(2))
        mp = re.search(r"Fecha de publicación:\s*(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2})", t, re.I)
        if mp:
            pub = mp.group(1)
        req_url, req_text = _find_requirement_href_and_text(tag)
        detalle_url = _find_detail_href_in_tag(tag)
        rows.append({"origen": "MENOR_8_UIT", "codigo": codigo, "entidad_contratante": entidad, "entidad": entidad, "tipo_objeto": tipo, "objeto": tipo, "descripcion": desc, "estado_portal": estado, "fecha_publicacion": pub, "cotizacion_inicio": cot_ini, "cotizacion_fin": cot_fin, "propuesta_fin": cot_fin, "requerimiento_pdf": req_url, "requerimiento_pdf_nombre": req_text, "detalle_url": detalle_url, "moneda": "Soles", "monto_estimado": 0})
        if len(rows) >= limit:
            break
    return _dedupe_columns(pd.DataFrame(rows))


def _collect_detail_urls_from_listing(driver, df, diagnostics):
    try:
        mapping = driver.execute_script("""
            function normText(s){ return (s||'').replace(/\s+/g,' ').trim(); }
            function buildHref(el){
                if (!el) return '';
                return el.getAttribute('href') || el.getAttribute('routerlink') || el.getAttribute('ng-reflect-router-link') || el.getAttribute('data-url') || el.getAttribute('data-href') || '';
            }
            function getDetailIn(card){
                const els = Array.from(card.querySelectorAll('a,button,span,div'));
                for (const el of els){
                    const href = buildHref(el);
                    const text = normText((el.innerText||'') + ' ' + (el.title||'') + ' ' + href);
                    if (text.toLowerCase().includes('ver detalle') || href.includes('contratacion-detalle')) return href;
                }
                return '';
            }
            const blocks = Array.from(document.querySelectorAll('div,section,article,li,tr'))
                .filter(el => (el.innerText||'').includes('CM-') && ((el.innerText||'').includes('Cotizaciones:') || (el.innerText||'').includes('Fecha de publicación')));
            blocks.sort((a,b) => (a.innerText||'').length - (b.innerText||'').length);
            const out = {};
            const seen = new Set();
            for (const card of blocks){
                const t = normText(card.innerText||'');
                const m = t.match(/CM-[A-Z0-9\-\/]+/);
                if (!m) continue;
                const code = m[0];
                if (seen.has(code)) continue;
                seen.add(code);
                let href = getDetailIn(card);
                out[code] = href || '';
            }
            return out;
        """) or {}
        hits = 0
        if not df.empty:
            for idx, row in df.iterrows():
                codigo = str(row.get("codigo", ""))
                url = _build_detail_url(mapping.get(codigo, ""))
                if url:
                    df.at[idx, "detalle_url"] = url
                    hits += 1
        diagnostics.append(f"URLs de detalle capturadas desde listado: {hits}/{len(df)}")
    except Exception as e:
        diagnostics.append(f"Error capturando URLs de detalle desde listado: {type(e).__name__} - {e}")
    return _dedupe_columns(df)


def _wait_detail_page(driver, codigo="", seconds=90):
    end = time.time() + seconds
    seen_detail_url = False
    while time.time() < end:
        cur = driver.current_url.lower()
        try:
            txt = _clean(BeautifulSoup(driver.page_source, "html.parser").get_text(" ", strip=True))
        except Exception:
            txt = ""
        if "contratacion-detalle" in cur:
            seen_detail_url = True
            if any(s in txt for s in ["Detalle de contratación", "Detalle de la contratación", "Requerimientos", "Ítems registrados", "Items registrados", "Imprimir", "Atrás"]):
                time.sleep(5)
                return True
        elif "Detalle de contratación" in txt or "Detalle de la contratación" in txt:
            time.sleep(5)
            return True
        time.sleep(1)
    return seen_detail_url


def _open_detail_direct(driver, detail_url, codigo, diagnostics, timeout=90):
    if not detail_url:
        diagnostics.append(f"Sin URL directa de detalle para {codigo}.")
        return False
    try:
        diagnostics.append(f"Abriendo detalle directo para {codigo}: {detail_url}")
        driver.get(detail_url)
        _wait_loader_gone(driver, timeout=30)
        if _wait_detail_page(driver, codigo, timeout):
            diagnostics.append(f"Detalle abierto directo para {codigo}.")
            return True
        diagnostics.append(f"No se confirmó página de detalle para {codigo}. URL actual={driver.current_url}")
        Path(f"debug_detalle_directo_fallido_{codigo}.html").write_text(driver.page_source, encoding="utf-8")
        return False
    except Exception as e:
        diagnostics.append(f"Error abriendo detalle directo para {codigo}: {type(e).__name__} - {e}")
        return False


def _parse_detail_table_rows(soup, info):
    found = False
    for tr in soup.find_all("tr"):
        cells = [_clean(c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        etapa = _norm(cells[0])
        f_ini = _extract_datetime(cells[1])
        f_fin = _extract_datetime(cells[2])
        if not f_ini or not f_fin:
            continue
        if "consulta" in etapa:
            info["consulta_inicio"], info["consulta_fin"] = f_ini, f_fin
            found = True
        elif "cotizacion" in etapa or "cotización" in etapa:
            info["cotizacion_inicio"], info["cotizacion_fin"] = f_ini, f_fin
            found = True
    return found


def _parse_detail_text_fallback(full, info):
    cron = full
    m = re.search(r"Cronograma\s+(.*?)(?:Listado de c[oó]digo|Requerimientos|Ítems registrados|Items registrados|$)", full, re.I)
    if m:
        cron = m.group(1)
    p = re.search(r"Consulta\s+.*?(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2})\s+(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2})\s+.*?Cotizaci[oó]n\s+.*?(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2})\s+(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2})", cron, re.I | re.S)
    if p:
        info["consulta_inicio"], info["consulta_fin"], info["cotizacion_inicio"], info["cotizacion_fin"] = p.group(1), p.group(2), p.group(3), p.group(4)
        return True
    fechas = re.findall(r"\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2}", cron)
    ncron = _norm(cron)
    if "consulta" in ncron and "cotizacion" in ncron and len(fechas) >= 4:
        info["consulta_inicio"], info["consulta_fin"], info["cotizacion_inicio"], info["cotizacion_fin"] = fechas[0], fechas[1], fechas[2], fechas[3]
        return True
    if "cotizacion" in ncron and len(fechas) >= 2:
        info["cotizacion_inicio"], info["cotizacion_fin"] = fechas[-2], fechas[-1]
        return True
    return False


def _parse_detail(html, expected_code=""):
    soup = BeautifulSoup(html, "html.parser")
    full = _clean(soup.get_text(" ", strip=True))
    info = {"codigo": expected_code, "entidad_contratante": "", "area_usuaria": "", "tipo_objeto": "", "descripcion": "", "fecha_publicacion": "", "consulta_inicio": "", "consulta_fin": "", "cotizacion_inicio": "", "cotizacion_fin": "", "requerimiento_pdf": "", "requerimiento_pdf_nombre": "", "detalle_texto": full[:5000]}
    mcod = re.search(r"(CM-[A-Z0-9\-\/]+)", full)
    if mcod:
        info["codigo"] = mcod.group(1)
    ment = re.search(r"Detalle de la contratación\s+(.*?)\s+Información general", full, re.I)
    if ment:
        info["entidad_contratante"] = _clean(ment.group(1))
    marea = re.search(r"Área usuaria:\s*(.*?)\s+(?:Servicio|Bien|Obra|Consultoría|Fecha de publicación)", full, re.I)
    if marea:
        info["area_usuaria"] = _clean(marea.group(1))
    mobj = re.search(r"(Servicio|Bien|Obra|Consultoría de Obra|Consultoria de Obra)\s*:\s*(.*?)\s+Fecha de publicación:", full, re.I)
    if mobj:
        info["tipo_objeto"], info["descripcion"] = _clean(mobj.group(1)), _clean(mobj.group(2))
    mpub = re.search(r"Fecha de publicación:\s*(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2})", full, re.I)
    if mpub:
        info["fecha_publicacion"] = mpub.group(1)
    if not _parse_detail_table_rows(soup, info):
        _parse_detail_text_fallback(full, info)
    for a in soup.find_all("a"):
        href = a.get("href") or ""
        txt = _clean(a.get_text(" ", strip=True))
        ntxt = _norm(txt)
        if "pdf" in href.lower() or "requerimiento" in ntxt or "tdr" in ntxt or "descargar" in ntxt:
            if href:
                info["requerimiento_pdf"] = urljoin(BASE_URL, href)
            info["requerimiento_pdf_nombre"] = txt
            break
    if not info["requerimiento_pdf_nombre"]:
        for el in soup.find_all(["button", "span", "div"]):
            txt = _clean(el.get_text(" ", strip=True))
            ntxt = _norm(txt)
            if "requerimiento" in ntxt or "tdr" in ntxt or "descargar" in ntxt:
                info["requerimiento_pdf_nombre"] = txt
                break
    return info


def _download_pdf_with_session(driver, pdf_url, codigo, link_text, diagnostics):
    if not pdf_url:
        return "", ""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = _filename_from_url_or_text(pdf_url, link_text, codigo)
    local_path = DOWNLOAD_DIR / filename
    try:
        session = requests.Session()
        for cookie in driver.get_cookies():
            session.cookies.set(cookie.get("name"), cookie.get("value"), domain=cookie.get("domain"))
        r = session.get(pdf_url, headers={"User-Agent": "Mozilla/5.0", "Referer": driver.current_url}, timeout=60, allow_redirects=True)
        ctype = r.headers.get("Content-Type", "").lower()
        if r.status_code == 200 and ("pdf" in ctype or r.content[:4] == b"%PDF"):
            local_path.write_bytes(r.content)
            diagnostics.append(f"PDF descargado por HTTP: {local_path}")
            return str(local_path), filename
        diagnostics.append(f"HTTP PDF no válido: status={r.status_code}, content-type={ctype}")
    except Exception as e:
        diagnostics.append(f"Error HTTP PDF: {type(e).__name__} - {e}")
    return "", ""


def _click_download_requirement(driver, codigo, diagnostics, timeout=45):
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    watch_dirs = [DOWNLOAD_DIR]
    user_downloads = Path.home() / "Downloads"
    if user_downloads.exists():
        watch_dirs.append(user_downloads)
    before = {d: {p.name for p in d.glob("*")} for d in watch_dirs}
    js = """
    const all = Array.from(document.querySelectorAll('a,button,span,div'));
    function norm(s){return (s||'').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');}
    for (const el of all) {
      const txt = norm((el.innerText||'') + ' ' + (el.title||'') + ' ' + (el.getAttribute('href')||''));
      if (txt.includes('descargar requerimiento') || txt.includes('requerimiento') || txt.includes('tdr') || txt.includes('.pdf') || txt.includes('descargar')) return el;
    }
    return null;
    """
    clicked = _safe_click(driver, driver.execute_script(js))
    if not clicked:
        diagnostics.append(f"No se encontró botón/link descargable para {codigo}.")
        return "", ""
    end = time.time() + timeout
    while time.time() < end:
        for d in watch_dirs:
            files = [p for p in d.glob("*") if not p.name.endswith(".crdownload") and not p.name.endswith(".tmp")]
            new_files = [p for p in files if p.name not in before.get(d, set())]
            if new_files:
                latest = max(new_files, key=lambda p: p.stat().st_mtime)
                target = DOWNLOAD_DIR / _sanitize_filename(f"{codigo}_{latest.name}")
                if latest.resolve() != target.resolve():
                    try:
                        target.write_bytes(latest.read_bytes())
                    except Exception:
                        try:
                            latest.rename(target)
                        except Exception:
                            pass
                diagnostics.append(f"PDF descargado por click: {target}")
                return str(target), target.name
        time.sleep(1)
    diagnostics.append(f"No se detectó descarga local para {codigo} después del click.")
    return "", ""


def _infer_estado(row):
    now = pd.Timestamp.now()
    consulta_fin = _to_dt(row.get("consulta_fin", ""))
    cotizacion_fin = _to_dt(row.get("cotizacion_fin", ""))
    estado_portal = _norm(row.get("estado_portal", ""))
    if "culmin" in estado_portal or "cerrad" in estado_portal:
        return "Cerrado", "🔴"
    if pd.notna(cotizacion_fin) and now <= cotizacion_fin:
        if pd.notna(consulta_fin) and now <= consulta_fin:
            return "Vigente para Consulta y Cotización", "🟢"
        return "Vigente sólo para Cotización", "🟡"
    if "evalu" in estado_portal:
        return "En Evaluación", "🟠"
    if pd.notna(cotizacion_fin) and now > cotizacion_fin:
        return "En Evaluación", "🟠"
    if "vigente" in estado_portal:
        return "Vigente sólo para Cotización", "🟡"
    return "Revisar", "🟠"


def _infer_estado_operativo(row):
    estado = str(row.get("estado_comercial", ""))
    situacion_cot = str(row.get("situacion_cotizacion", ""))
    if "Vence hoy" in situacion_cot:
        return "Vence Hoy"
    if "Vigente" in estado:
        return "Vigente"
    if "Evaluación" in estado or "Evaluacion" in estado:
        return "En Evaluación"
    if "Cerrado" in estado:
        return "Cerrado"
    return "Revisar"


def _apply_runtime_fields(df):
    for idx, row in df.iterrows():
        estado, vig = _infer_estado(row)
        df.at[idx, "estado_comercial"] = estado
        df.at[idx, "vigencia"] = vig
        df.at[idx, "dias_para_consulta"] = _dias_hasta(row.get("consulta_fin", ""))
        df.at[idx, "dias_para_cotizacion"] = _dias_hasta(row.get("cotizacion_fin", ""))
        df.at[idx, "dias_para_propuesta"] = df.at[idx, "dias_para_cotizacion"]
        df.at[idx, "horas_para_consulta"] = _horas_hasta(row.get("consulta_fin", ""))
        df.at[idx, "horas_para_cotizacion"] = _horas_hasta(row.get("cotizacion_fin", ""))
        df.at[idx, "situacion_consulta"] = _situacion_vencimiento(row.get("consulta_fin", ""))
        df.at[idx, "situacion_cotizacion"] = _situacion_vencimiento(row.get("cotizacion_fin", ""))
        df.at[idx, "estado_operativo"] = _infer_estado_operativo(df.loc[idx])
        if row.get("cotizacion_inicio", ""):
            df.at[idx, "propuesta_inicio"] = row.get("cotizacion_inicio", "")
        if row.get("cotizacion_fin", ""):
            df.at[idx, "propuesta_fin"] = row.get("cotizacion_fin", "")
        if not row.get("nomenclatura", ""):
            df.at[idx, "nomenclatura"] = row.get("codigo", "")
    return _dedupe_columns(df)


def search_menor8_browser(auth_url=MENOR8_AUTH_URL, search_url=MENOR8_SEARCH_URL, keyword="satelital", headless=False, max_wait=60, login_wait_seconds=300, max_results=50, enrich_details=True, download_requirements=True) -> Tuple[pd.DataFrame, List[str]]:
    diagnostics = []
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    for opt in ["--start-maximized", "--disable-notifications", "--disable-popup-blocking", "--ignore-certificate-errors"]:
        options.add_argument(opt)
    prefs = {"download.default_directory": str(DOWNLOAD_DIR.resolve()), "download.prompt_for_download": False, "download.directory_upgrade": True, "plugins.always_open_pdf_externally": True}
    options.add_experimental_option("prefs", prefs)
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get(search_url)
        diagnostics.append(f"GET menores: {search_url}")
        _wait_loader_gone(driver, timeout=30)
        if not _wait_for_search_page(driver, max_wait, diagnostics, "buscador inicial"):
            if not _wait_manual_login(driver, auth_url, login_wait_seconds, diagnostics):
                return pd.DataFrame(), diagnostics
        driver.get(search_url)
        _wait_loader_gone(driver, timeout=30)
        _wait_for_search_page(driver, max_wait, diagnostics, "buscador post-login")
        if not _is_search_page(driver):
            diagnostics.append("Aún no se encuentra en el buscador final.")
            return pd.DataFrame(), diagnostics
        diagnostics.append(f"URL final buscador: {driver.current_url}")
        _force_keyword_search(driver, keyword, diagnostics)
        ok_filtered = _wait_filtered_results_loaded(driver, keyword, max_wait, diagnostics, max_allowed_total=1000)
        if not ok_filtered:
            diagnostics.append("No se parsea listado porque no se confirmó filtro efectivo.")
            return pd.DataFrame(), diagnostics
        Path("respuesta_menores.html").write_text(driver.page_source, encoding="utf-8")
        df = _parse_list_cards(driver.page_source, limit=max_results)
        diagnostics.append(f"Contratos menores detectados: {len(df)}")
        if df.empty:
            return df, diagnostics
        df = _collect_detail_urls_from_listing(driver, df, diagnostics)
        missing = int((df.get("detalle_url", pd.Series(dtype=str)).fillna("").astype(str) == "").sum()) if "detalle_url" in df.columns else len(df)
        if missing:
            diagnostics.append(f"Procesos sin URL directa de detalle tras captura inicial: {missing}")
        if enrich_details:
            for idx, row in df.iterrows():
                codigo = row.get("codigo", "")
                detalle_url = row.get("detalle_url", "")
                try:
                    if not detalle_url:
                        diagnostics.append(f"Se omite detalle de {codigo}: no hay URL directa de detalle.")
                        continue
                    if not _open_detail_direct(driver, detalle_url, codigo, diagnostics, timeout=90):
                        diagnostics.append(f"No se pudo abrir detalle directo para {codigo}.")
                        continue
                    info = _parse_detail(driver.page_source, codigo)
                    Path(f"respuesta_menores_detalle_{idx}.html").write_text(driver.page_source, encoding="utf-8")
                    for k, v in info.items():
                        if v:
                            df.at[idx, k] = v
                    df.at[idx, "detalle_url"] = driver.current_url
                    if not info.get("consulta_fin"):
                        full_dbg = _clean(BeautifulSoup(driver.page_source, "html.parser").get_text(" ", strip=True))
                        m_dbg = re.search(r"Cronograma\s+(.*?)(?:Listado de c[oó]digo|Requerimientos|Ítems registrados|Items registrados|$)", full_dbg, re.I)
                        if m_dbg:
                            df.at[idx, "cronograma_debug"] = m_dbg.group(1)[:1200]
                    if download_requirements:
                        pdf_url = df.at[idx, "requerimiento_pdf"] if "requerimiento_pdf" in df.columns else ""
                        pdf_name = df.at[idx, "requerimiento_pdf_nombre"] if "requerimiento_pdf_nombre" in df.columns else ""
                        local_path, local_name = _download_pdf_with_session(driver, pdf_url, codigo, pdf_name, diagnostics)
                        if not local_path:
                            local_path, local_name = _click_download_requirement(driver, codigo, diagnostics)
                        if local_path:
                            df.at[idx, "requerimiento_pdf_local"] = local_path
                            df.at[idx, "requerimiento_pdf_archivo"] = local_name
                    diagnostics.append(f"Detalle menor {idx}: {codigo} consulta_fin={df.at[idx].get('consulta_fin','')} cotizacion_fin={df.at[idx].get('cotizacion_fin','')}")
                except Exception as e:
                    diagnostics.append(f"Error detalle menor {codigo}: {type(e).__name__} - {e}")
        if not df.empty:
            df = _apply_runtime_fields(df)
            df = _dedupe_columns(df)
        return df, diagnostics
    except Exception as e:
        diagnostics.append(f"Error Menores 8 UIT: {type(e).__name__} - {e}")
        return pd.DataFrame(), diagnostics
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
