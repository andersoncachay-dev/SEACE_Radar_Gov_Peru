
from typing import List, Tuple
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

SEACE_PUBLIC_URL = "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml"
TIMEOUT = 60


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 SEACE-Radar/0.4",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
    })
    return s


def _inputs_payload(soup):
    payload = {}
    for tag in soup.find_all(["input", "select", "textarea"]):
        name = tag.get("name")
        if not name:
            continue
        if tag.name == "select":
            selected = tag.find("option", selected=True)
            payload[name] = selected.get("value", "") if selected else ""
        elif tag.get("type") in ["checkbox", "radio"]:
            if tag.has_attr("checked"):
                payload[name] = tag.get("value", "on")
        else:
            payload[name] = tag.get("value", "")
    return payload


def _find_field_by_label(soup, label_keywords):
    labels = soup.find_all(text=True)
    best = []
    for txt in labels:
        clean = " ".join(str(txt).split()).lower()
        if all(k.lower() in clean for k in label_keywords):
            parent = txt.parent
            for _ in range(5):
                if parent is None:
                    break
                controls = parent.find_all(["input", "select", "textarea"])
                for c in controls:
                    if c.get("name"):
                        best.append(c.get("name"))
                parent = parent.parent
    return best[0] if best else None


def _set_first_matching(payload, soup, possible_labels, value):
    if value in [None, ""]:
        return None
    for labels in possible_labels:
        name = _find_field_by_label(soup, labels)
        if name:
            payload[name] = value
            return name
    # fallback by name contains
    lower_map = {k.lower(): k for k in payload.keys()}
    for labels in possible_labels:
        joined = " ".join(labels).lower().replace(" ", "")
        for low, original in lower_map.items():
            if any(token in low for token in joined.split()):
                payload[original] = value
                return original
    return None


def _choose_select_option(soup, payload, field_name, desired_text):
    if not field_name or not desired_text:
        return
    sel = soup.find("select", attrs={"name": field_name})
    if not sel:
        payload[field_name] = desired_text
        return
    desired = desired_text.lower().strip()
    for opt in sel.find_all("option"):
        text = opt.get_text(" ", strip=True).lower()
        value = opt.get("value", "")
        if desired == text or desired in text:
            payload[field_name] = value
            return
    payload[field_name] = desired_text


def _find_buttons(soup):
    buttons = []
    for tag in soup.find_all(["button", "input", "a"]):
        text = tag.get_text(" ", strip=True) or tag.get("value", "") or tag.get("title", "")
        name = tag.get("name") or tag.get("id")
        if text or name:
            buttons.append({"tag": tag.name, "text": text, "name": name, "id": tag.get("id"), "class": " ".join(tag.get("class", []))})
    return buttons


def _parse_tables(html):
    try:
        tables = pd.read_html(html)
    except Exception:
        tables = []
    candidates = []
    for t in tables:
        cols = " ".join(map(str, t.columns)).lower()
        body = " ".join(map(str, t.head(5).values.flatten())).lower()
        if any(k in cols + body for k in ["entidad", "nomenclatura", "objeto", "requerimiento", "publicacion", "descripción", "descripcion"]):
            candidates.append(t)
    if candidates:
        return max(candidates, key=len)
    return pd.DataFrame()


def _normalize_seace_table(df):
    if df.empty:
        return df
    # flatten multiindex columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [" ".join(str(x) for x in col if str(x) != "nan").strip() for col in df.columns]
    df = df.copy()
    df.columns = [" ".join(str(c).split()) for c in df.columns]
    return df


def search_seace_public(url=SEACE_PUBLIC_URL, keyword="satelital", objeto="Servicio", year="2026", version="Seace 3", mode="procedimientos") -> Tuple[pd.DataFrame, List[str]]:
    diagnostics = []
    s = _session()
    try:
        r = s.get(url, timeout=TIMEOUT)
        diagnostics.append(f"GET {r.url} -> {r.status_code} / {r.headers.get('content-type')}")
        r.raise_for_status()
    except Exception as e:
        return pd.DataFrame(), [f"Error GET inicial: {type(e).__name__} - {e}"]

    soup = BeautifulSoup(r.text, "html.parser")
    payload = _inputs_payload(soup)
    diagnostics.append(f"Inputs detectados: {len(payload)}")

    # campos por etiquetas visibles en la pantalla SEACE
    field_desc = _set_first_matching(payload, soup, [["descripción", "objeto"], ["descripcion", "objeto"], ["descripción", "requerimiento"], ["descripcion", "requerimiento"]], keyword)
    field_year = _set_first_matching(payload, soup, [["año", "convocatoria"], ["anio", "convocatoria"], ["año"]], year)
    field_obj = _set_first_matching(payload, soup, [["objeto", "contratación"], ["objeto", "contratacion"]], objeto)
    field_ver = _set_first_matching(payload, soup, [["version", "seace"], ["versión", "seace"]], version)

    _choose_select_option(soup, payload, field_obj, objeto)
    _choose_select_option(soup, payload, field_year, year)
    _choose_select_option(soup, payload, field_ver, version)

    diagnostics.append(f"Campo descripcion usado: {field_desc}")
    diagnostics.append(f"Campo objeto usado: {field_obj}")
    diagnostics.append(f"Campo año usado: {field_year}")
    diagnostics.append(f"Campo version usado: {field_ver}")

    buttons = _find_buttons(soup)
    search_buttons = [b for b in buttons if "buscar" in str(b).get("text", "").lower() or "buscar" in str(b).get("name", "").lower()]
    diagnostics.append(f"Botones Buscar detectados: {search_buttons[:3]}")

    # Try JSF command submit variants
    post_urls = [r.url, url]
    submitted = False
    response_texts = []
    for btn in search_buttons[:3] or [{}]:
        post_payload = dict(payload)
        if btn.get("name"):
            post_payload[btn["name"]] = btn.get("name")
        elif btn.get("id"):
            post_payload[btn["id"]] = btn.get("id")
        for post_url in post_urls:
            try:
                pr = s.post(post_url, data=post_payload, timeout=TIMEOUT, headers={"Referer": r.url})
                diagnostics.append(f"POST {post_url} -> {pr.status_code} / {pr.headers.get('content-type')} / len={len(pr.text)}")
                response_texts.append(pr.text)
                df = _normalize_seace_table(_parse_tables(pr.text))
                if not df.empty:
                    diagnostics.append(f"Tabla detectada por POST: {len(df)} filas")
                    return df, diagnostics
                submitted = True
            except Exception as e:
                diagnostics.append(f"Error POST {post_url}: {type(e).__name__} - {e}")

    # Fallback: parse initial page (sometimes contains prior results)
    df = _normalize_seace_table(_parse_tables(r.text))
    if not df.empty:
        diagnostics.append(f"Tabla detectada en HTML inicial: {len(df)} filas")
        return df, diagnostics

    diagnostics.append("No se detectaron tablas de resultados. Probable causa: evento JSF/PrimeFaces especifico, AJAX parcial o CAPTCHA/reCAPTCHA.")
    diagnostics.append("Siguiente ajuste: capturar en DevTools la solicitud XHR que se genera al pulsar Buscar o Exportar a Excel.")
    return pd.DataFrame(), diagnostics
