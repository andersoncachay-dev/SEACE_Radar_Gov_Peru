
from typing import Tuple, List
import time
import re
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

SEACE_PUBLIC_URL = "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml"
PROCESS_FORM = "tbBuscador:idFormBuscarProceso"


def _version_value(version: str) -> str:
    text = str(version or "").lower()
    if "3" in text: return "3"
    if "2" in text: return "2"
    return str(version or "")


def _set_input_like_user(driver, element_id: str, value: str) -> bool:
    try:
        el = driver.find_element(By.ID, element_id)
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.2)
        try:
            el.click(); el.send_keys(Keys.CONTROL, "a"); el.send_keys(Keys.BACKSPACE); el.send_keys(str(value))
        except Exception: pass
        driver.execute_script("""
            const el = document.getElementById(arguments[0]);
            if (el) { el.value = arguments[1]; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); el.dispatchEvent(new Event('blur',{bubbles:true})); }
        """, element_id, str(value))
        return True
    except Exception: return False


def _click_like_user(driver, element_id: str) -> bool:
    try:
        el = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, element_id)))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el); time.sleep(0.5)
        try: ActionChains(driver).move_to_element(el).pause(0.2).click(el).perform()
        except Exception: driver.execute_script("arguments[0].click();", el)
        return True
    except Exception: return False


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _looks_like_data_row(cells: List[str]) -> bool:
    if not cells or len(cells) < 8: return False
    if not re.fullmatch(r"\d{1,3}", cells[0]): return False
    text = " ".join(cells).upper()
    return any(token in text for token in ["SATELITAL","SAN GABAN","MARINA DE GUERRA","BCRP","FUERZA AEREA","GEOFISICO","EJERCITO","UCAYALI","APURIMAC"])


def _row_to_dict(cells: List[str]) -> dict:
    cells = [_clean_text(c) for c in cells if _clean_text(c) != ""]
    if len(cells) >= 10 and cells[5].lower() in ["bien","servicio","obra","consultoría de obra","consultoria de obra"]:
        n, entidad, fecha, nomen, reiniciado, objeto, desc, monto, moneda, version = cells[:10]
        acciones = cells[10] if len(cells) > 10 else ""
    elif len(cells) >= 9:
        n, entidad, fecha, nomen, objeto, desc, monto, moneda, version = cells[:9]
        reiniciado = ""; acciones = cells[9] if len(cells) > 9 else ""
    else:
        return {}
    return {
        "N°": n,
        "RUC": "",
        "Nombre o Sigla de la Entidad": entidad,
        "Fecha y Hora de Publicacion": fecha,
        "Nomenclatura": nomen,
        "Reiniciado Desde": reiniciado,
        "Objeto de Contratación": objeto,
        "Descripción de Objeto": desc,
        "Código SNIP": "",
        "Código Único de Inversión": "",
        "VR / VE / Cuantía de la contratación": monto,
        "Moneda": moneda,
        "Versión SEACE": version,
        "Acciones": acciones,
        "url_detalle": "",
    }


def _parse_primefaces_grid(html: str):
    soup = BeautifulSoup(html, "html.parser")
    rows=[]
    for tr in soup.find_all("tr"):
        cells=[_clean_text(td.get_text(" ", strip=True)) for td in tr.find_all(["td","th"])]
        cells=[c for c in cells if c]
        if _looks_like_data_row(cells):
            rows.append(cells)
    clean_rows=[r for r in rows if 8 <= len(r) <= 13 and re.fullmatch(r"\d{1,3}", r[0])]
    if clean_rows: rows=clean_rows
    data=[]
    for cells in rows:
        d=_row_to_dict(cells)
        if d: data.append(d)
    seen=set(); deduped=[]
    for d in data:
        key=(d.get("N°"),d.get("Nomenclatura"),d.get("Nombre o Sigla de la Entidad"))
        if key not in seen:
            seen.add(key); deduped.append(d)
    return pd.DataFrame(deduped), rows[:5]


def _parse_tables(html: str):
    with open("debug_browser.html", "w", encoding="utf-8", errors="ignore") as f: f.write(html)
    df2, sample_rows = _parse_primefaces_grid(html)
    if not df2.empty: return df2, 0, [("primefaces_rows", len(df2), len(df2.columns), sample_rows)]
    try: tables = pd.read_html(html)
    except Exception: tables=[]
    return pd.DataFrame(), len(tables), []


def _normalize(df):
    if df.empty: return df
    if isinstance(df.columns, pd.MultiIndex): df.columns=[" ".join(str(x) for x in col if str(x)!="nan").strip() for col in df.columns]
    df=df.copy(); df.columns=[" ".join(str(c).split()) for c in df.columns]
    return df


def _parse_date_from_text(text: str):
    if not text: return ""
    m = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})(?:\s+\d{1,2}:\d{2})?", text)
    return m.group(1) if m else ""


def _parse_detail_page(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    full = _clean_text(soup.get_text(" ", strip=True))
    info = {"ruc":"", "fecha_presentacion":"", "fecha_buena_pro":"", "fecha_fin":"", "estado_comercial":"", "vigencia":""}

    # RUC: busca cualquier número de 11 dígitos cercano a N° Ruc / Entidad Contratante
    ruc_match = re.search(r"N[°º]?\s*Ruc\s+(\d{11})", full, re.IGNORECASE)
    if not ruc_match:
        ruc_match = re.search(r"\b(20\d{9}|10\d{9})\b", full)
    if ruc_match:
        info["ruc"] = ruc_match.group(1)

    # Cronograma: recorrer filas y tomar Fecha Fin de etapas relevantes
    for tr in soup.find_all("tr"):
        cells = [_clean_text(td.get_text(" ", strip=True)) for td in tr.find_all(["td","th"])]
        if len(cells) >= 3:
            etapa = cells[0].lower()
            fecha_fin = cells[-1]
            if "presentaci" in etapa and "propuesta" in etapa:
                info["fecha_presentacion"] = _parse_date_from_text(fecha_fin) or _parse_date_from_text(" ".join(cells))
            if "buena pro" in etapa:
                info["fecha_buena_pro"] = _parse_date_from_text(fecha_fin) or _parse_date_from_text(" ".join(cells))
                info["fecha_fin"] = info["fecha_buena_pro"]

    return info


def _infer_estado(fecha_presentacion: str, fecha_buena_pro: str, monto, nomenclatura: str):
    today = pd.Timestamp.today().normalize()
    if fecha_buena_pro:
        return "Cerrado", "🔴"
    if fecha_presentacion:
        fp = pd.to_datetime(fecha_presentacion, dayfirst=True, errors="coerce")
        if pd.notna(fp):
            if fp.normalize() >= today:
                return "Vigente", "🟢"
            return "En evaluación", "🟡"
    # Heurística: RES-PROC suele tener proceso posterior/cerrado o por adjudicación, y montos ya publicados deben revisarse.
    nom = str(nomenclatura or "").upper()
    try: m = float(monto or 0)
    except Exception: m = 0
    if "RES-PROC" in nom or m > 0:
        return "Revisar", "🟠"
    return "Vigente", "🟢"


def _enrich_details(driver, df: pd.DataFrame, max_details: int, diagnostics: List[str]):
    # V7 deja el mecanismo preparado. Si las URLs de detalle se capturan en versiones futuras, se abrirán aquí.
    # Mientras tanto, aplica lógica de estado por fechas/monto/nomenclatura.
    for idx, row in df.head(max_details).iterrows():
        estado, vig = _infer_estado(row.get("fecha_presentacion",""), row.get("fecha_buena_pro",""), row.get("monto",0), row.get("Nomenclatura", row.get("nomenclatura","")))
        df.at[idx, "Estado Comercial"] = estado
        df.at[idx, "Vigencia"] = vig
    return df


def search_seace_public_browser(url=SEACE_PUBLIC_URL, keyword="satelital", year="2026", version="Seace 3", headless=False, max_wait=45, enrich_details=False, max_details=10) -> Tuple[pd.DataFrame, List[str]]:
    diagnostics=[]; options=Options()
    if headless: options.add_argument("--headless=new")
    options.add_argument("--start-maximized"); options.add_argument("--disable-notifications"); options.add_argument("--disable-popup-blocking"); options.add_argument("--ignore-certificate-errors")
    driver=None
    try:
        driver=webdriver.Chrome(options=options); wait=WebDriverWait(driver,max_wait); driver.get(url); diagnostics.append(f"GET navegador: {url}")
        time.sleep(3); tabs=driver.find_elements(By.XPATH, "//*[contains(text(),'Buscador de Procedimientos de Selección')]")
        if tabs: driver.execute_script("arguments[0].click();", tabs[0]); diagnostics.append("Pestaña Procedimientos seleccionada"); time.sleep(3)
        desc_id=f"{PROCESS_FORM}:descripcionObjeto"; wait.until(EC.presence_of_element_located((By.ID, desc_id)))
        driver.execute_script("const active=document.getElementById('tbBuscador_activeIndex'); if(active) active.value='1';")
        ok_desc=_set_input_like_user(driver, desc_id, keyword); ok_year=_set_input_like_user(driver, f"{PROCESS_FORM}:anioConvocatoria_input", str(year)); _set_input_like_user(driver, f"{PROCESS_FORM}:anioConvocatoria_focus", str(year)); ok_ver=_set_input_like_user(driver, f"{PROCESS_FORM}:j_idt247_input", _version_value(version))
        diagnostics += [f"Descripción seteada: {ok_desc} -> {keyword}", f"Año seteado: {ok_year} -> {year}", f"Versión seteada: {ok_ver} -> {_version_value(version)}"]
        clicked=False
        for bid in [f"{PROCESS_FORM}:btnBuscarSelToken", f"{PROCESS_FORM}:btnBuscarSel"]:
            if _click_like_user(driver,bid): diagnostics.append(f"Click botón: {bid}"); clicked=True; break
        if not clicked: diagnostics.append("No se encontró botón Buscar por ID; intentando submit del formulario"); driver.execute_script("document.getElementById(arguments[0]).submit();", PROCESS_FORM)
        end=time.time()+max_wait; last_len=0; best_info=[]
        while time.time()<end:
            time.sleep(1); html=driver.page_source
            if len(html)!=last_len: last_len=len(html); diagnostics.append(f"HTML len actual: {last_len}")
            df,tables_count,candidates_info=_parse_tables(html); best_info=candidates_info
            if not df.empty:
                with open("respuesta_seace_browser.html","w",encoding="utf-8",errors="ignore") as f: f.write(html)
                df=_normalize(df)
                # Ensure status columns exist and infer base state
                for col in ["RUC", "Fecha Presentacion", "Fecha Buena Pro", "Fecha Fin", "Estado Comercial", "Vigencia"]:
                    if col not in df.columns: df[col]=""
                for idx, row in df.iterrows():
                    estado, vig = _infer_estado(row.get("Fecha Presentacion",""), row.get("Fecha Buena Pro",""), row.get("VR / VE / Cuantía de la contratación",0), row.get("Nomenclatura",""))
                    df.at[idx, "Estado Comercial"] = estado
                    df.at[idx, "Vigencia"] = vig
                if enrich_details:
                    diagnostics.append(f"Enriquecimiento de detalle solicitado para máximo {max_details} procesos; URLs de detalle no disponibles en grilla, aplicando inferencia local.")
                    df = _enrich_details(driver, df, max_details=max_details, diagnostics=diagnostics)
                diagnostics.append(f"Tablas HTML detectadas: {tables_count}"); diagnostics.append(f"Candidatas: {candidates_info}"); diagnostics.append(f"Tabla detectada navegador: {len(df)} filas / {len(df.columns)} columnas")
                return df, diagnostics
        html=driver.page_source
        with open("respuesta_seace_browser.html","w",encoding="utf-8",errors="ignore") as f: f.write(html)
        df,tables_count,candidates_info=_parse_tables(html); diagnostics.append(f"Tablas HTML al final: {tables_count}"); diagnostics.append(f"Candidatas al final: {candidates_info or best_info}"); diagnostics.append("No se detectó tabla con navegador.")
        return pd.DataFrame(), diagnostics
    except Exception as e:
        diagnostics.append(f"Error navegador: {type(e).__name__} - {e}"); return pd.DataFrame(), diagnostics
    finally:
        try:
            if driver: driver.quit()
        except Exception: pass
