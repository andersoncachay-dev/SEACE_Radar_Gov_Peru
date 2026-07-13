# -*- coding: utf-8 -*-
"""SEACE Radar Gov Peru - Menores a 8 UIT v12.4

Flujo consolidado:
- Login manual y aceptacion de terminos.
- Busqueda por palabra clave.
- Validacion estricta del filtro.
- Lectura de primera pagina.
- Click en tarjeta de cada proceso.
- Deteccion exacta del link/boton "Ver detalle" dentro de la tarjeta seleccionada.
- Apertura del detalle, extraccion de cronograma/PDF y retorno con espera de 30s.

Nota: esta version evita devolver el contenedor raiz de Angular como boton.
"""
from __future__ import annotations

from typing import Tuple, List
import json
import re
import time
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


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value):
    txt = _clean(value).lower()
    return txt.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u").replace("ñ", "n")


def _dedupe_columns(df):
    try:
        return df.loc[:, ~df.columns.duplicated()].copy()
    except Exception:
        return df


def _extract_datetime(text):
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2}|\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}|\d{1,2}/\d{1,2}/\d{4})", str(text or ""))
    return m.group(1) if m else ""


def _to_dt(value):
    if not value:
        return pd.NaT
    return pd.to_datetime(value, dayfirst=True, errors="coerce")


def _dias_hasta(value):
    dt = _to_dt(value)
    if pd.isna(dt): return ""
    return int((dt.normalize() - pd.Timestamp.now().normalize()).days)


def _horas_hasta(value):
    dt = _to_dt(value)
    if pd.isna(dt): return ""
    return round((dt - pd.Timestamp.now()).total_seconds() / 3600, 2)


def _situacion_vencimiento(value):
    dt = _to_dt(value)
    if pd.isna(dt): return ""
    now = pd.Timestamp.now()
    if now <= dt:
        return "Vence hoy" if now.normalize() == dt.normalize() else "Vigente"
    return "Vencido hoy" if now.normalize() == dt.normalize() else "Vencido"


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
        base += ".pdf"
    return _sanitize_filename(f"{codigo}_{base}")


def _is_search_page(driver):
    url = driver.current_url.lower()
    return "/cotizacion/contrataciones" in url and "contratacion-detalle" not in url and "auth-proveedor" not in url


def _is_terms_page(driver):
    url = driver.current_url.lower()
    html = driver.page_source.lower()
    return "terminos-condiciones" in url or "términos y condiciones" in html or "terminos y condiciones" in html or "política de privacidad" in html


def _wait_loader_gone(driver, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        try:
            visible = driver.execute_script("""
                const overlays = Array.from(document.querySelectorAll('.screen-loader-overlay,[role="dialog"],.cdk-overlay-backdrop,.loading,.loader'));
                return overlays.some(el => {
                    const st = window.getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    return st.display !== 'none' && st.visibility !== 'hidden' && Number(st.opacity || 1) > 0 && r.width > 0 && r.height > 0;
                });
            """)
            if not visible: return True
        except Exception:
            return True
        time.sleep(0.5)
    return False


def _safe_click(driver, element):
    if element is None: return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", element)
        time.sleep(0.25)
        ActionChains(driver).move_to_element(element).pause(0.15).click(element).perform()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception:
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


def _accept_terms_if_present(driver, diagnostics):
    if not _is_terms_page(driver): return False
    diagnostics.append("Términos y condiciones detectados.")
    try:
        for chk in driver.find_elements(By.XPATH, "//input[@type='checkbox']"):
            try:
                if not chk.is_selected():
                    _safe_click(driver, chk)
                    break
            except Exception:
                pass
        time.sleep(0.5)
        elems = driver.find_elements(By.XPATH, "//*[self::button or self::a or self::span or self::div][contains(normalize-space(.),'Acepto')]")
        for el in elems:
            if "No Acepto" in _clean(el.text): continue
            if _safe_click(driver, el):
                diagnostics.append("Términos aceptados automáticamente.")
                time.sleep(3)
                return True
    except Exception as exc:
        diagnostics.append(f"No se pudo aceptar términos: {type(exc).__name__} - {exc}")
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
    return driver.execute_script("""
        const inputs = Array.from(document.querySelectorAll('input'));
        for (const i of inputs) {
            const txt = ((i.placeholder||'')+' '+(i.ariaLabel||'')+' '+(i.name||'')+' '+(i.id||'')).toLowerCase();
            if (txt.includes('buscar') || txt.includes('descrip') || txt.includes('requerimiento') || txt.includes('numero') || txt.includes('entidad')) return i;
        }
        return inputs.length ? inputs[0] : null;
    """)


def _click_search(driver):
    el = driver.execute_script("""
        const candidates = Array.from(document.querySelectorAll('button,a,span,img'));
        function n(s){return (s||'').toLowerCase();}
        for (const el of candidates) {
            const txt = n(el.innerText)+' '+n(el.title)+' '+n(el.alt)+' '+n(el.className);
            if (txt.includes('buscar') || txt.includes('search') || txt.includes('lupa') || txt.includes('fa-search')) return el;
        }
        return null;
    """)
    return _safe_click(driver, el)


def _force_keyword_search(driver, keyword, diagnostics):
    _wait_loader_gone(driver, timeout=30)
    inp = _find_search_input(driver)
    if not inp:
        diagnostics.append("No se encontró input de búsqueda para reaplicar filtro.")
        return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inp)
        time.sleep(0.2)
        driver.execute_script("""
            const i = arguments[0]; const value = arguments[1];
            i.focus();
            i.value = '';
            i.dispatchEvent(new Event('input', {bubbles:true}));
            i.dispatchEvent(new Event('change', {bubbles:true}));
            i.value = value;
            i.dispatchEvent(new Event('input', {bubbles:true}));
            i.dispatchEvent(new Event('change', {bubbles:true}));
        """, inp, keyword)
        time.sleep(0.3)
        if not _click_search(driver):
            try: inp.send_keys(Keys.ENTER)
            except Exception:
                driver.execute_script("""
                    const i = arguments[0];
                    i.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', bubbles:true}));
                    i.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', code:'Enter', bubbles:true}));
                """, inp)
        diagnostics.append(f"Filtro reaplicado: {keyword}")
        return True
    except Exception as exc:
        diagnostics.append(f"Error reaplicando filtro {keyword}: {type(exc).__name__} - {exc}")
        return False


def _get_registered_count(driver):
    try:
        txt = _clean(BeautifulSoup(driver.page_source, "html.parser").get_text(" ", strip=True))
        m = re.search(r"Contrataciones registradas\s*\((\d+)\)", txt, re.I)
        if m: return int(m.group(1))
    except Exception:
        pass
    return None


def _card_texts(driver, limit=10):
    try:
        return driver.execute_script("""
            const blocks = Array.from(document.querySelectorAll('div,section,article,li,tr'))
                .filter(el => (el.innerText||'').includes('CM-') && ((el.innerText||'').includes('Cotizaciones:') || (el.innerText||'').includes('Fecha de publicación')));
            blocks.sort((a,b) => (a.innerText||'').length - (b.innerText||'').length);
            const seen = new Set(); const out = [];
            for (const el of blocks) {
                const t = (el.innerText||'').replace(/\s+/g,' ').trim();
                const m = t.match(/CM-[A-Z0-9\-\/]+/);
                if (!m || seen.has(m[0])) continue;
                seen.add(m[0]); out.push(t);
                if (out.length >= arguments[0]) break;
            }
            return out;
        """, limit) or []
    except Exception:
        return []


def _filter_is_effective(driver, keyword, max_allowed_total=1000):
    try:
        total = _get_registered_count(driver)
        if total is not None and total > max_allowed_total: return False
        txt = _clean(BeautifulSoup(driver.page_source, "html.parser").get_text(" ", strip=True))
        if "CM-" not in txt: return False
        cards = _card_texts(driver, limit=10)
        if keyword and cards and not any(keyword.lower() in c.lower() for c in cards): return False
        return True
    except Exception:
        return False


def _wait_filtered_results_loaded(driver, keyword, seconds, diagnostics, max_allowed_total=1000):
    end = time.time() + seconds
    last_total = None
    while time.time() < end:
        _wait_loader_gone(driver, timeout=10)
        total = _get_registered_count(driver)
        last_total = total if total is not None else last_total
        txt = _clean(BeautifulSoup(driver.page_source, "html.parser").get_text(" ", strip=True))
        if "Contrataciones registradas" in txt and "CM-" in txt:
            if total is not None and total > max_allowed_total:
                diagnostics.append(f"Filtro perdido detectado. Total visible={total}. Reaplicando '{keyword}'.")
                _force_keyword_search(driver, keyword, diagnostics)
                time.sleep(1)
                continue
            if _filter_is_effective(driver, keyword, max_allowed_total=max_allowed_total):
                diagnostics.append(f"Resultados filtrados correctamente para '{keyword}'. Total visible={total}")
                return True
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


def _parse_list_cards(html, limit=50):
    soup = BeautifulSoup(html, "html.parser")
    rows, seen = [], set()
    for tag in soup.find_all(["div", "section", "article", "li"]):
        t = _clean(tag.get_text(" ", strip=True))
        if "CM-" not in t or not any(x in t for x in ["Cotizaciones:", "Fecha de publicación", "Ver detalle", "Descargar requerimiento"]):
            continue
        m = re.search(r"(?:\d+\.\s*)?(CM-[A-Z0-9\-\/]+)", t)
        if not m: continue
        codigo = m.group(1)
        if codigo in seen: continue
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
        if mp: pub = mp.group(1)
        req_url, req_text = _find_requirement_href_and_text(tag)
        rows.append({
            "origen":"MENOR_8_UIT", "codigo":codigo, "nomenclatura":codigo,
            "entidad":entidad, "entidad_contratante":entidad,
            "objeto":tipo, "tipo_objeto":tipo, "descripcion":desc,
            "estado_portal":estado, "fecha_publicacion":pub,
            "cotizacion_inicio":cot_ini, "cotizacion_fin":cot_fin,
            "propuesta_inicio":cot_ini, "propuesta_fin":cot_fin,
            "monto":0, "monto_estimado":0, "moneda":"Soles",
            "requerimiento_pdf":req_url, "requerimiento_pdf_nombre":req_text,
            "detalle_url":"", "url_detalle":""
        })
        if len(rows) >= limit: break
    return _dedupe_columns(pd.DataFrame(rows))


def _find_process_card(driver, codigo):
    return driver.execute_script("""
        const codigo = arguments[0];
        const all = Array.from(document.querySelectorAll('div,section,article,li,tr'));
        function txt(el){ return (el && el.innerText) ? el.innerText : ''; }
        const candidates = all.filter(el => {
            const t = txt(el);
            return t.includes(codigo) && (t.includes('Cotizaciones:') || t.includes('Fecha de publicación') || t.includes('Ver detalle'));
        });
        candidates.sort((a,b) => txt(a).length - txt(b).length);
        if (candidates.length) return candidates[0];
        const codeNode = all.find(el => txt(el).includes(codigo));
        if (!codeNode) return null;
        let p = codeNode;
        for (let i=0; i<10 && p; i++) {
            const t = txt(p);
            if (t.includes(codigo) && (t.includes('Cotizaciones:') || t.includes('Fecha de publicación') || t.includes('Ver detalle'))) return p;
            p = p.parentElement;
        }
        return codeNode;
    """, codigo)


def _select_process_for_actions(driver, codigo, diagnostics, timeout=12):
    card = _find_process_card(driver, codigo)
    if not card:
        diagnostics.append(f"No se encontró tarjeta completa para {codigo}.")
        Path(f"debug_sin_tarjeta_{codigo}.html").write_text(driver.page_source, encoding="utf-8")
        return None
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", card)
        time.sleep(0.6)
        target = driver.execute_script("""
            const card = arguments[0]; const codigo = arguments[1];
            const els = Array.from(card.querySelectorAll('div,span,p,b,strong,a,button'));
            for (const el of els) { if ((el.innerText||'').includes(codigo)) return el; }
            return card;
        """, card, codigo)
        _safe_click(driver, target)
        end = time.time() + timeout
        while time.time() < end:
            body_text = driver.execute_script("return document.body.innerText || '';" ) or ""
            merged = _norm(body_text)
            if "ver detalle" in merged or "descargar requerimiento" in merged or "consultas" in merged:
                diagnostics.append(f"Proceso seleccionado y acciones visibles para {codigo}.")
                return card
            time.sleep(0.5)
        diagnostics.append(f"Proceso seleccionado, pero las acciones no se confirmaron para {codigo}; se intentará click directo en Ver detalle.")
        return card
    except Exception as exc:
        diagnostics.append(f"Error seleccionando proceso {codigo}: {type(exc).__name__} - {exc}")
        return card


def _find_detail_control(driver, card, codigo):
    return driver.execute_script("""
        const card = arguments[0]; const codigo = arguments[1];
        function norm(s){ return (s||'').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,''); }
        function isVisible(el){ const r=el.getBoundingClientRect(); const st=getComputedStyle(el); return r.width>0 && r.height>0 && st.visibility!='hidden' && st.display!='none'; }
        function isClickableCandidate(el){
            if (!el || !isVisible(el)) return false;
            const tag=(el.tagName||'').toLowerCase(); const role=el.getAttribute('role')||'';
            const href=el.getAttribute('href')||el.getAttribute('routerlink')||el.getAttribute('ng-reflect-router-link')||'';
            const cls=el.getAttribute('class')||'';
            return tag==='a'||tag==='button'||role==='button'||href||cls.includes('btn')||cls.includes('link')||cls.includes('cursor-pointer');
        }
        function closestClickable(el){
            let p=el;
            for(let i=0;i<10 && p && p!==document.body;i++){
                if(isClickableCandidate(p)) return p;
                p=p.parentElement;
            }
            return el;
        }
        function detailScore(el){
            const text=norm((el.innerText||el.textContent||'').trim());
            const href=el.getAttribute('href')||el.getAttribute('routerlink')||el.getAttribute('ng-reflect-router-link')||'';
            if(href.includes('contratacion-detalle')) return 1000;
            if(text==='ver detalle') return 900;
            if(text.includes('ver detalle') && text.length <= 80) return 800;
            if(text.includes('open_in_new') && text.includes('ver detalle') && text.length <= 160) return 700;
            return 0;
        }
        let candidates=[];
        let scopeEls=Array.from(card.querySelectorAll('a,button,span,div,mat-icon,i,svg'));
        for(const el of scopeEls){
            const score=detailScore(el);
            if(score>0) candidates.push({el:closestClickable(el), score:score, len:((el.innerText||el.textContent||'').trim().length)});
        }
        if(candidates.length===0){
            // buscar por bloque que contiene codigo, luego elementos cercanos
            const all=Array.from(document.querySelectorAll('a,button,span,div,mat-icon,i,svg'));
            const idx=all.findIndex(el => (el.innerText||el.textContent||'').includes(codigo));
            const start=idx>=0?Math.max(0,idx-20):0; const end=idx>=0?Math.min(all.length,idx+240):all.length;
            for(let i=start;i<end;i++){
                const score=detailScore(all[i]);
                if(score>0) candidates.push({el:closestClickable(all[i]), score:score, len:((all[i].innerText||all[i].textContent||'').trim().length)});
            }
        }
        candidates=candidates.filter(c=>c.el && isVisible(c.el));
        // eliminar contenedores enormes: si contiene todo el buscador no es el link
        candidates=candidates.filter(c => ((c.el.innerText||c.el.textContent||'').length < 300 || (c.el.tagName||'').toLowerCase()==='a' || (c.el.tagName||'').toLowerCase()==='button'));
        candidates.sort((a,b)=> b.score-a.score || a.len-b.len);
        return candidates.length ? candidates[0].el : null;
    """, card, codigo)


def _page_has_detail_content(driver):
    try:
        txt = _clean(BeautifulSoup(driver.page_source, "html.parser").get_text(" ", strip=True))
        norm = _norm(txt)
        return any(s in norm for s in ["detalle de contratacion","detalle de la contratacion","informacion general","cronograma","requerimientos","items registrados","imprimir","atras"])
    except Exception:
        return False


def _wait_detail_page(driver, codigo="", seconds=90):
    end = time.time() + seconds
    seen_url = False
    while time.time() < end:
        cur = driver.current_url.lower()
        if "contratacion-detalle" in cur: seen_url = True
        if seen_url or _page_has_detail_content(driver):
            time.sleep(5)
            return True
        time.sleep(1)
    return seen_url


def _capture_dom_debug(driver, card, detail_el, codigo, diagnostics):
    try:
        data = driver.execute_script("""
            const card=arguments[0], el=arguments[1];
            function attrs(node){ if(!node) return {}; const out={}; for(const a of Array.from(node.attributes||[])) out[a.name]=a.value; return out; }
            function shortHtml(node){ return node ? (node.outerHTML||'').slice(0,12000) : ''; }
            const ancestors=[]; let p=el;
            for(let i=0;i<8 && p;i++){ ancestors.push({level:i, tag:p.tagName, text:(p.innerText||p.textContent||'').trim(), attrs:attrs(p), outer:shortHtml(p)}); p=p.parentElement; }
            return {url:location.href, buttonText:(el?(el.innerText||el.textContent||'').trim():''), buttonAttrs:attrs(el), buttonOuter:shortHtml(el), cardText:(card?(card.innerText||card.textContent||'').trim():''), cardOuter:shortHtml(card), ancestors:ancestors};
        """, card, detail_el)
        Path(f"debug_ver_detalle_dom_{codigo}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        Path(f"debug_card_outerhtml_{codigo}.html").write_text(data.get("cardOuter", ""), encoding="utf-8")
        Path(f"debug_ver_detalle_outerhtml_{codigo}.html").write_text(data.get("buttonOuter", ""), encoding="utf-8")
        diagnostics.append(f"DOM Ver detalle capturado para {codigo}: debug_ver_detalle_dom_{codigo}.json")
        diagnostics.append(f"Ver detalle attrs {codigo}: {str(data.get('buttonAttrs', {}))[:500]}")
        diagnostics.append(f"Ver detalle outer preview {codigo}: {_clean(data.get('buttonOuter',''))[:500]}")
    except Exception as exc:
        diagnostics.append(f"No se pudo capturar DOM de Ver detalle para {codigo}: {type(exc).__name__} - {exc}")


def _try_click_and_wait(driver, codigo, label, click_fn, diagnostics, wait_seconds=10):
    try:
        before = driver.current_url
        result = click_fn()
        end = time.time() + wait_seconds
        while time.time() < end:
            _wait_loader_gone(driver, timeout=2)
            after = driver.current_url
            if "contratacion-detalle" in after.lower() or after != before or _page_has_detail_content(driver):
                diagnostics.append(f"Click Angular {label} para {codigo}: éxito, before={before}, after={after}, result={result}")
                return True
            time.sleep(0.5)
        diagnostics.append(f"Click Angular {label} para {codigo}: sin navegación/render, before={before}, after={driver.current_url}, result={result}")
    except Exception as exc:
        diagnostics.append(f"Click Angular {label} falló para {codigo}: {type(exc).__name__} - {exc}")
    return False


def _angular_click_variants(driver, detail_el, diagnostics, codigo):
    if _try_click_and_wait(driver, codigo, "safe_click", lambda: _safe_click(driver, detail_el), diagnostics): return True
    if _try_click_and_wait(driver, codigo, "element.click()", lambda: driver.execute_script("arguments[0].click(); return true;", detail_el), diagnostics): return True
    if _try_click_and_wait(driver, codigo, "MouseEvent center sequence", lambda: driver.execute_script("""
        const el=arguments[0]; const r=el.getBoundingClientRect(); const x=Math.floor(r.left+r.width/2), y=Math.floor(r.top+r.height/2);
        ['pointerdown','mousedown','pointerup','mouseup','click'].forEach(type => el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:x,clientY:y})));
        return {x:x,y:y,tag:el.tagName,text:(el.innerText||el.textContent||'').trim()};
    """, detail_el), diagnostics): return True
    if _try_click_and_wait(driver, codigo, "ActionChains center", lambda: driver.execute_script("arguments[0].scrollIntoView({block:'center'});", detail_el) or ActionChains(driver).move_to_element(detail_el).pause(0.2).click().perform() or True, diagnostics): return True
    try:
        href = driver.execute_script("""
            let p=arguments[0];
            for(let i=0;i<10 && p;i++){ const h=p.getAttribute('href')||p.getAttribute('routerlink')||p.getAttribute('ng-reflect-router-link')||p.getAttribute('data-url')||p.getAttribute('data-href')||''; if(h) return h; p=p.parentElement; }
            return '';
        """, detail_el) or ""
        if href:
            diagnostics.append(f"Href/routerLink detectado en Ver detalle para {codigo}: {href}")
            if href.startswith("http"): url=href
            elif href.startswith("/"): url=BASE_URL+href
            elif "contratacion-detalle" in href: url=BASE_URL+"/cotizacion/contrataciones/"+href.lstrip("/")
            else: url=""
            if url:
                driver.get(url)
                if _wait_detail_page(driver, codigo, 30):
                    diagnostics.append(f"Detalle abierto por href/routerLink para {codigo}: {url}")
                    return True
    except Exception as exc:
        diagnostics.append(f"Fallback href/routerLink falló para {codigo}: {type(exc).__name__} - {exc}")
    return False


def _open_detail_by_sequential_click(driver, codigo, diagnostics, timeout=90):
    card = _select_process_for_actions(driver, codigo, diagnostics, timeout=12)
    if not card: return False
    detail_el = _find_detail_control(driver, card, codigo)
    if not detail_el:
        diagnostics.append(f"No se encontró control Ver detalle para {codigo} después de seleccionar tarjeta.")
        Path(f"debug_sin_ver_detalle_{codigo}.html").write_text(driver.page_source, encoding="utf-8")
        return False
    _capture_dom_debug(driver, card, detail_el, codigo, diagnostics)
    old_url = driver.current_url
    diagnostics.append(f"Click en Ver detalle para {codigo} con selector exacto V12.4.")
    if _angular_click_variants(driver, detail_el, diagnostics, codigo):
        if _wait_detail_page(driver, codigo, timeout):
            diagnostics.append(f"Detalle abierto/renderizado para {codigo}.")
            return True
    try:
        handles = driver.window_handles
        if len(handles) > 1:
            driver.switch_to.window(handles[-1])
            if _wait_detail_page(driver, codigo, 30):
                diagnostics.append(f"Detalle abierto en nueva pestaña para {codigo}.")
                return True
    except Exception:
        pass
    Path(f"debug_click_detalle_fallido_{codigo}.html").write_text(driver.page_source, encoding="utf-8")
    diagnostics.append(f"Click Ver detalle no logró detalle para {codigo}. URL anterior={old_url}, URL actual={driver.current_url}. Se guardó debug_click_detalle_fallido_{codigo}.html")
    return False



def _extract_requirement_from_detail_dom(driver, codigo, diagnostics):
    """V12.5: extrae link/nombre de PDF desde el DOM del detalle Angular.

    El detalle puede renderizar el requerimiento como enlace visual sin que BeautifulSoup
    lo capture correctamente en page_source en el momento del parseo.
    """
    try:
        data = driver.execute_script("""
            const links = Array.from(document.querySelectorAll('a,button,span,div'));
            function norm(s){return (s||'').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');}
            for (const el of links) {
                const text = (el.innerText || el.textContent || '').trim();
                const href = el.getAttribute('href') || el.getAttribute('data-href') || el.getAttribute('data-url') || '';
                const title = el.getAttribute('title') || '';
                const merged = norm(text + ' ' + href + ' ' + title);
                if (merged.includes('.pdf') || merged.includes('requerimiento') || merged.includes('tdr') || merged.includes('descargar')) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {
                        return {text:text, href:href, title:title, outer:(el.outerHTML||'').slice(0,3000)};
                    }
                }
            }
            return {text:'', href:'', title:'', outer:''};
        """) or {}
        href = data.get('href') or ''
        text = data.get('text') or data.get('title') or ''
        if href:
            href = urljoin(BASE_URL, href)
        if data.get('outer'):
            Path(f"debug_requerimiento_dom_{codigo}.html").write_text(data.get('outer', ''), encoding='utf-8')
            diagnostics.append(f"DOM requerimiento capturado para {codigo}: debug_requerimiento_dom_{codigo}.html")
        return href, text
    except Exception as exc:
        diagnostics.append(f"No se pudo extraer requerimiento desde DOM para {codigo}: {type(exc).__name__} - {exc}")
        return '', ''


def _click_download_requirement_from_detail(driver, codigo, diagnostics, timeout=45):
    """V12.5: click específico sobre el enlace de requerimiento dentro del detalle."""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    watch_dirs = [DOWNLOAD_DIR]
    user_downloads = Path.home() / "Downloads"
    if user_downloads.exists():
        watch_dirs.append(user_downloads)
    before = {d: {p.name for p in d.glob("*")} for d in watch_dirs}
    try:
        el = driver.execute_script("""
            const links = Array.from(document.querySelectorAll('a,button,span,div'));
            function norm(s){return (s||'').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');}
            for (const el of links) {
                const text = (el.innerText || el.textContent || '').trim();
                const href = el.getAttribute('href') || el.getAttribute('data-href') || el.getAttribute('data-url') || '';
                const merged = norm(text + ' ' + href);
                if (merged.includes('.pdf') || merged.includes('requerimiento') || merged.includes('tdr') || merged.includes('descargar')) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) return el;
                }
            }
            return null;
        """)
        if not _safe_click(driver, el):
            diagnostics.append(f"No se encontró enlace visible de requerimiento en detalle para {codigo}.")
            return '', ''
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
                            pass
                    diagnostics.append(f"PDF descargado desde detalle por click: {target}")
                    return str(target), target.name
            time.sleep(1)
        diagnostics.append(f"No se detectó descarga local desde detalle para {codigo} después del click.")
        return '', ''
    except Exception as exc:
        diagnostics.append(f"Error click requerimiento detalle {codigo}: {type(exc).__name__} - {exc}")
        return '', ''

def _parse_detail_text_fallback(full, info):
    cron = full
    m = re.search(r"Cronograma\s+(.*?)(?:Listado de c[oó]digo|Requerimientos|Ítems registrados|Items registrados|$)", full, re.I)
    if m: cron = m.group(1)
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


def _parse_detail_table_rows(soup, info):
    found = False
    for tr in soup.find_all("tr"):
        cells = [_clean(c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
        if len(cells) < 3: continue
        etapa, f_ini, f_fin = _norm(cells[0]), _extract_datetime(cells[1]), _extract_datetime(cells[2])
        if not f_ini or not f_fin: continue
        if "consulta" in etapa:
            info["consulta_inicio"], info["consulta_fin"] = f_ini, f_fin; found = True
        elif "cotizacion" in etapa or "cotización" in etapa:
            info["cotizacion_inicio"], info["cotizacion_fin"] = f_ini, f_fin; found = True
    return found


def _parse_detail(html, expected_code=""):
    soup = BeautifulSoup(html, "html.parser")
    full = _clean(soup.get_text(" ", strip=True))
    info = {"codigo":expected_code, "nomenclatura":expected_code, "consulta_inicio":"", "consulta_fin":"", "cotizacion_inicio":"", "cotizacion_fin":"", "requerimiento_pdf":"", "requerimiento_pdf_nombre":"", "detalle_texto":full[:5000]}
    mcod = re.search(r"(CM-[A-Z0-9\-\/]+)", full)
    if mcod: info["codigo"] = info["nomenclatura"] = mcod.group(1)
    if not _parse_detail_table_rows(soup, info): _parse_detail_text_fallback(full, info)
    for a in soup.find_all("a"):
        href = a.get("href") or ""; txt = _clean(a.get_text(" ", strip=True)); ntxt = _norm(txt)
        if "pdf" in href.lower() or "requerimiento" in ntxt or "tdr" in ntxt or "descargar" in ntxt:
            if href: info["requerimiento_pdf"] = urljoin(BASE_URL, href)
            info["requerimiento_pdf_nombre"] = txt
            break
    return info


def _download_pdf_with_session(driver, pdf_url, codigo, link_text, diagnostics):
    if not pdf_url: return "", ""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = _filename_from_url_or_text(pdf_url, link_text, codigo)
    local_path = DOWNLOAD_DIR / filename
    try:
        session = requests.Session()
        for cookie in driver.get_cookies():
            session.cookies.set(cookie.get("name"), cookie.get("value"), domain=cookie.get("domain"))
        r = session.get(pdf_url, headers={"User-Agent":"Mozilla/5.0", "Referer":driver.current_url}, timeout=60, allow_redirects=True)
        ctype = r.headers.get("Content-Type", "").lower()
        if r.status_code == 200 and ("pdf" in ctype or r.content[:4] == b"%PDF"):
            local_path.write_bytes(r.content); diagnostics.append(f"PDF descargado por HTTP: {local_path}"); return str(local_path), filename
        diagnostics.append(f"HTTP PDF no válido: status={r.status_code}, content-type={ctype}")
    except Exception as exc:
        diagnostics.append(f"Error HTTP PDF: {type(exc).__name__} - {exc}")
    return "", ""


def _click_download_requirement(driver, codigo, diagnostics, timeout=45):
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    watch_dirs = [DOWNLOAD_DIR]
    user_downloads = Path.home() / "Downloads"
    if user_downloads.exists(): watch_dirs.append(user_downloads)
    before = {d:{p.name for p in d.glob("*")} for d in watch_dirs}
    el = driver.execute_script("""
        const all = Array.from(document.querySelectorAll('a,button,span,div'));
        function norm(s){return (s||'').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');}
        for (const el of all) {
            const txt = norm((el.innerText||'') + ' ' + (el.title||'') + ' ' + (el.getAttribute('href')||''));
            if (txt.includes('descargar requerimiento') || txt.includes('requerimiento') || txt.includes('tdr') || txt.includes('.pdf') || txt.includes('descargar')) return el;
        }
        return null;
    """)
    if not _safe_click(driver, el):
        diagnostics.append(f"No se encontró botón/link descargable para {codigo}."); return "", ""
    end = time.time() + timeout
    while time.time() < end:
        for d in watch_dirs:
            files = [p for p in d.glob("*") if not p.name.endswith(".crdownload") and not p.name.endswith(".tmp")]
            new_files = [p for p in files if p.name not in before.get(d, set())]
            if new_files:
                latest = max(new_files, key=lambda p:p.stat().st_mtime)
                target = DOWNLOAD_DIR / _sanitize_filename(f"{codigo}_{latest.name}")
                if latest.resolve() != target.resolve():
                    try: target.write_bytes(latest.read_bytes())
                    except Exception: pass
                diagnostics.append(f"PDF descargado por click: {target}"); return str(target), target.name
        time.sleep(1)
    diagnostics.append(f"No se detectó descarga local para {codigo} después del click.")
    return "", ""


def _return_to_listing_after_detail(driver, search_url, keyword, max_wait, diagnostics):
    try:
        diagnostics.append("Regresando al listado con Atrás y esperando reconstrucción del portal.")
        driver.back()
    except Exception as exc:
        diagnostics.append(f"driver.back() falló: {type(exc).__name__} - {exc}; cargando buscador.")
        driver.get(search_url)
    time.sleep(30)
    _wait_loader_gone(driver, timeout=30)
    if not _is_search_page(driver):
        driver.get(search_url); _wait_for_search_page(driver, max_wait, diagnostics, "buscador retorno")
    total = _get_registered_count(driver)
    if total is not None and total > 1000:
        diagnostics.append(f"Listado volvió a total masivo={total}; reaplicando '{keyword}'.")
        _force_keyword_search(driver, keyword, diagnostics); _wait_filtered_results_loaded(driver, keyword, max_wait, diagnostics, max_allowed_total=1000)
    elif not _filter_is_effective(driver, keyword, max_allowed_total=1000):
        diagnostics.append(f"Filtro no vigente tras Atrás; reaplicando '{keyword}'.")
        _force_keyword_search(driver, keyword, diagnostics); _wait_filtered_results_loaded(driver, keyword, max_wait, diagnostics, max_allowed_total=1000)
    else:
        diagnostics.append(f"Listado filtrado vigente tras Atrás. Total visible={total}")
    return True


def _infer_estado(row):
    now = pd.Timestamp.now()
    consulta_fin = _to_dt(row.get("consulta_fin", "")); cotizacion_fin = _to_dt(row.get("cotizacion_fin", "")); estado_portal = _norm(row.get("estado_portal", ""))
    if "culmin" in estado_portal or "cerrad" in estado_portal: return "Cerrado", "Rojo"
    if pd.notna(cotizacion_fin) and now <= cotizacion_fin:
        if pd.notna(consulta_fin) and now <= consulta_fin: return "Vigente para Consulta y Cotización", "Verde"
        return "Vigente sólo para Cotización", "Amarillo"
    if "evalu" in estado_portal: return "En Evaluación", "Naranja"
    if pd.notna(cotizacion_fin) and now > cotizacion_fin: return "En Evaluación", "Naranja"
    if "vigente" in estado_portal: return "Vigente sólo para Cotización", "Amarillo"
    return "Revisar", "Naranja"


def _apply_runtime_fields(df):
    # Normaliza por si app.py arma columnas con alias repetidos.
    df = _dedupe_columns(df)
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
        if not row.get("nomenclatura", ""): df.at[idx, "nomenclatura"] = row.get("codigo", "")
        df.at[idx, "estado_operativo"] = "Vigente" if "Vigente" in estado else ("Cerrado" if "Cerrado" in estado else "En Evaluación")
    return _dedupe_columns(df)


def search_menor8_browser(auth_url=MENOR8_AUTH_URL, search_url=MENOR8_SEARCH_URL, keyword="satelital", headless=False, max_wait=60, login_wait_seconds=300, max_results=50, enrich_details=True, download_requirements=True) -> Tuple[pd.DataFrame, List[str]]:
    diagnostics = []
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    options = Options()
    if headless: options.add_argument("--headless=new")
    for opt in ["--start-maximized", "--disable-notifications", "--disable-popup-blocking", "--ignore-certificate-errors"]: options.add_argument(opt)
    prefs = {"download.default_directory":str(DOWNLOAD_DIR.resolve()), "download.prompt_for_download":False, "download.directory_upgrade":True, "plugins.always_open_pdf_externally":True}
    options.add_experimental_option("prefs", prefs)
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get(search_url); diagnostics.append(f"GET menores: {search_url}")
        _wait_loader_gone(driver, timeout=30)
        if not _wait_for_search_page(driver, max_wait, diagnostics, "buscador inicial"):
            if not _wait_manual_login(driver, auth_url, login_wait_seconds, diagnostics): return pd.DataFrame(), diagnostics
        driver.get(search_url); _wait_loader_gone(driver, timeout=30); _wait_for_search_page(driver, max_wait, diagnostics, "buscador post-login")
        if not _is_search_page(driver): diagnostics.append("Aún no se encuentra en el buscador final."); return pd.DataFrame(), diagnostics
        diagnostics.append(f"URL final buscador: {driver.current_url}")
        _force_keyword_search(driver, keyword, diagnostics)
        ok_filtered = _wait_filtered_results_loaded(driver, keyword, max_wait, diagnostics, max_allowed_total=1000)
        if not ok_filtered: diagnostics.append("No se parsea listado porque no se confirmó filtro efectivo."); return pd.DataFrame(), diagnostics
        Path("respuesta_menores.html").write_text(driver.page_source, encoding="utf-8")
        df = _parse_list_cards(driver.page_source, limit=max_results); df = _dedupe_columns(df)
        diagnostics.append(f"Primera lectura de página completada. Contratos menores detectados: {len(df)}")
        if df.empty: return df, diagnostics
        codigos = [str(c) for c in df.get("codigo", pd.Series(dtype=str)).dropna().tolist()]
        diagnostics.append(f"Códigos a procesar secuencialmente: {', '.join(codigos)}")
        if enrich_details:
            for idx, codigo in enumerate(codigos):
                try:
                    if not _is_search_page(driver): driver.get(search_url); _wait_for_search_page(driver, max_wait, diagnostics, "buscador antes de caso")
                    if not _filter_is_effective(driver, keyword, max_allowed_total=1000):
                        diagnostics.append(f"Filtro no vigente antes de {codigo}. Total={_get_registered_count(driver)}. Reaplicando '{keyword}'.")
                        _force_keyword_search(driver, keyword, diagnostics); _wait_filtered_results_loaded(driver, keyword, max_wait, diagnostics, max_allowed_total=1000)
                    else:
                        diagnostics.append(f"Filtro vigente antes de procesar {codigo}. Total={_get_registered_count(driver)}")
                    if not _open_detail_by_sequential_click(driver, codigo, diagnostics, timeout=90):
                        diagnostics.append(f"No se pudo abrir detalle por flujo secuencial para {codigo}."); continue
                    info = _parse_detail(driver.page_source, codigo)
                    # V12.5: complementar PDF/TDR desde DOM Angular del detalle si BeautifulSoup no lo capturó.
                    if not info.get("requerimiento_pdf"):
                        dom_pdf_url, dom_pdf_name = _extract_requirement_from_detail_dom(driver, codigo, diagnostics)
                        if dom_pdf_url:
                            info["requerimiento_pdf"] = dom_pdf_url
                        if dom_pdf_name:
                            info["requerimiento_pdf_nombre"] = dom_pdf_name
                    Path(f"respuesta_menores_detalle_{idx}.html").write_text(driver.page_source, encoding="utf-8")
                    row_mask = df["codigo"].astype(str).eq(codigo); row_idx = df.index[row_mask][0] if row_mask.any() else idx
                    for k, v in info.items():
                        if v: df.at[row_idx, k] = v
                    df.at[row_idx, "detalle_url"] = driver.current_url; df.at[row_idx, "url_detalle"] = driver.current_url
                    if download_requirements:
                        pdf_url = df.at[row_idx, "requerimiento_pdf"] if "requerimiento_pdf" in df.columns else ""
                        pdf_name = df.at[row_idx, "requerimiento_pdf_nombre"] if "requerimiento_pdf_nombre" in df.columns else ""
                        local_path, local_name = _download_pdf_with_session(driver, pdf_url, codigo, pdf_name, diagnostics)
                        if not local_path: local_path, local_name = _click_download_requirement_from_detail(driver, codigo, diagnostics)
                        if not local_path: local_path, local_name = _click_download_requirement(driver, codigo, diagnostics)
                        if local_path: df.at[row_idx, "requerimiento_pdf_local"] = local_path; df.at[row_idx, "requerimiento_pdf_archivo"] = local_name
                    diagnostics.append(f"Detalle menor {idx}: {codigo} consulta_fin={df.loc[row_idx].get('consulta_fin','')} cotizacion_fin={df.loc[row_idx].get('cotizacion_fin','')}")
                    _return_to_listing_after_detail(driver, search_url, keyword, max_wait, diagnostics)
                except Exception as exc:
                    diagnostics.append(f"Error detalle menor {codigo}: {type(exc).__name__} - {exc}")
                    try: _return_to_listing_after_detail(driver, search_url, keyword, max_wait, diagnostics)
                    except Exception: pass
        if not df.empty: df = _apply_runtime_fields(df); df = _dedupe_columns(df)
        return df, diagnostics
    except Exception as exc:
        diagnostics.append(f"Error Menores 8 UIT: {type(exc).__name__} - {exc}")
        return pd.DataFrame(), diagnostics
    finally:
        try:
            if driver: driver.quit()
        except Exception: pass
