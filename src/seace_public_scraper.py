from typing import List, Tuple
import pandas as pd
import requests
from bs4 import BeautifulSoup

SEACE_PUBLIC_URL = "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml"
TIMEOUT = 60
PROCESS_FORM = "tbBuscador:idFormBuscarProceso"


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 SEACE-Radar/0.7",
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


def _find_buttons(soup):
    buttons = []
    for tag in soup.find_all(["button", "input", "a"]):
        text = tag.get_text(" ", strip=True) or tag.get("value", "") or tag.get("title", "")
        name = tag.get("name") or tag.get("id")
        if text or name:
            buttons.append({
                "tag": tag.name,
                "text": str(text or ""),
                "name": str(name or ""),
                "id": str(tag.get("id") or ""),
                "class": " ".join(tag.get("class", [])),
            })
    return buttons


def _parse_tables(html):
    try:
        tables = pd.read_html(html)
    except Exception:
        tables = []

    candidates = []
    for t in tables:
        cols = " ".join(map(str, t.columns)).lower()
        body = " ".join(map(str, t.head(10).values.flatten())).lower()
        signature = cols + " " + body
        # Tabla de resultados de procesos SEACE suele contener estas columnas/textos.
        if any(k in signature for k in [
            "entidad", "nomenclatura", "objeto", "descrip", "publicacion", "publicación",
            "versión seace", "version seace", "acciones", "cuantía", "cuantia"
        ]):
            candidates.append(t)

    if candidates:
        # Normalmente la tabla de resultados es la mayor tabla candidata.
        return max(candidates, key=lambda x: (len(x), len(x.columns)))
    return pd.DataFrame()


def _normalize_seace_table(df):
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [" ".join(str(x) for x in col if str(x) != "nan").strip() for col in df.columns]
    df = df.copy()
    df.columns = [" ".join(str(c).split()) for c in df.columns]
    return df


def _safe_get(obj, key, default=""):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def _version_value(version: str) -> str:
    text = str(version or "").lower()
    if "3" in text:
        return "3"
    if "2" in text:
        return "2"
    return str(version or "")


def _force_process_search_payload(payload, keyword, year, version):
    """Configura exclusivamente el formulario Buscador de Procedimientos de Seleccion.

    Hallazgo del debug:
    - El formulario correcto es tbBuscador:idFormBuscarProceso.
    - descripcionObjeto, anioConvocatoria_input y j_idt247_input ya aparecen en el payload.
    - tbBuscador_activeIndex debe ser 1 para dejar activa la pestana de Procedimientos.
    """
    payload["tbBuscador_activeIndex"] = "1"

    # Asegurar que el formulario correcto sea enviado.
    payload[PROCESS_FORM] = PROCESS_FORM
    payload[f"{PROCESS_FORM}:numPositionTabView"] = "1"

    # Campos del formulario correcto observados en tu PAYLOAD DETECTADO.
    payload[f"{PROCESS_FORM}:descripcionObjeto"] = keyword
    payload[f"{PROCESS_FORM}:anioConvocatoria_input"] = str(year)
    payload[f"{PROCESS_FORM}:anioConvocatoria_focus"] = str(year)
    payload[f"{PROCESS_FORM}:j_idt247_input"] = _version_value(version)

    # Limpiar campos potencialmente confundidos de otros tabs para no lanzar ACF/otros formularios.
    for k in list(payload.keys()):
        kl = str(k).lower()
        if "idformbuscaracf" in kl and "descripcionobjeto" in kl:
            payload[k] = ""
    return payload


def _find_process_search_buttons(buttons):
    preferred = []
    fallback = []
    for b in buttons:
        if not isinstance(b, dict):
            continue
        name = str(b.get("name", ""))
        bid = str(b.get("id", ""))
        text = str(b.get("text", "")).lower()
        haystack = f"{name} {bid}".lower()
        if PROCESS_FORM.lower() in haystack and ("btnbuscar" in haystack or "buscar" in text):
            preferred.append(b)
        elif "btnbuscar" in haystack or "buscar" in text:
            fallback.append(b)
    return preferred or fallback


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
    payload = _force_process_search_payload(payload, keyword=keyword, year=year, version=version)

    print("\n" + "=" * 80)
    print("PAYLOAD PROCESO SEACE")
    print("=" * 80)
    for k, v in payload.items():
        if k.startswith(PROCESS_FORM) or k == "tbBuscador_activeIndex" or k == "javax.faces.ViewState":
            print(k, "=", v)
    print("=" * 80 + "\n")

    diagnostics.append(f"Inputs detectados: {len(payload)}")
    diagnostics.append(f"Formulario usado: {PROCESS_FORM}")
    diagnostics.append(f"Descripcion proceso: {payload.get(PROCESS_FORM + ':descripcionObjeto')}")
    diagnostics.append(f"Año proceso: {payload.get(PROCESS_FORM + ':anioConvocatoria_input')}")
    diagnostics.append(f"Version proceso: {payload.get(PROCESS_FORM + ':j_idt247_input')}")

    buttons = _find_buttons(soup)
    diagnostics.append(f"Botones totales detectados: {len(buttons)}")
    search_buttons = _find_process_search_buttons(buttons)
    diagnostics.append(f"Botones Buscar proceso detectados: {search_buttons[:5]}")

    post_urls = [r.url]
    if url != r.url:
        post_urls.append(url)

    # Probar solo botones del formulario correcto primero.
    for btn in (search_buttons[:5] if search_buttons else [{}]):
        if not isinstance(btn, dict):
            continue
        post_payload = dict(payload)
        btn_name = _safe_get(btn, "name", "")
        btn_id = _safe_get(btn, "id", "")
        if btn_name:
            post_payload[btn_name] = btn_name
        elif btn_id:
            post_payload[btn_id] = btn_id

        diagnostics.append(f"Submit usado: {btn}")

        for post_url in post_urls:
            try:
                pr = s.post(post_url, data=post_payload, timeout=TIMEOUT, headers={"Referer": r.url})
                with open("respuesta_seace.html", "w", encoding="utf-8", errors="ignore") as f:
                    f.write(pr.text)
                diagnostics.append(f"POST {post_url} -> {pr.status_code} / {pr.headers.get('content-type')} / len={len(pr.text)}")

                df = _normalize_seace_table(_parse_tables(pr.text))
                if not df.empty:
                    diagnostics.append(f"Tabla detectada por POST: {len(df)} filas / {len(df.columns)} columnas")
                    return df, diagnostics
            except Exception as e:
                diagnostics.append(f"Error POST {post_url}: {type(e).__name__} - {e}")

    # Fallback: intentar leer cualquier tabla cargada en la respuesta inicial.
    df = _normalize_seace_table(_parse_tables(r.text))
    if not df.empty:
        diagnostics.append(f"Tabla detectada en HTML inicial: {len(df)} filas")
        return df, diagnostics

    diagnostics.append("No se detectaron tablas de resultados en respuesta_seace.html.")
    diagnostics.append("Si el navegador manual si devuelve tabla, falta replicar exactamente el evento JSF/PrimeFaces del boton Buscar o el token/captcha.")
    return pd.DataFrame(), diagnostics
