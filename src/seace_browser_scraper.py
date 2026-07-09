
from typing import Tuple, List
import time
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

SEACE_PUBLIC_URL = "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml"
PROCESS_FORM = "tbBuscador:idFormBuscarProceso"


def _version_value(version: str) -> str:
    text = str(version or "").lower()
    if "3" in text: return "3"
    if "2" in text: return "2"
    return str(version or "")


def _set_value_js(driver, element_id, value):
    driver.execute_script("""
        const el = document.getElementById(arguments[0]);
        if (el) {
            el.value = arguments[1];
            el.dispatchEvent(new Event('input', {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
        }
    """, element_id, value)


def _click_if_exists(driver, element_id):
    try:
        el = driver.find_element(By.ID, element_id)
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.4)
        driver.execute_script("arguments[0].click();", el)
        return True
    except Exception:
        return False


def _parse_tables(html):
    try:
        tables = pd.read_html(html)
    except Exception:
        tables = []
    candidates = []
    for t in tables:
        cols = " ".join(map(str, t.columns)).lower()
        body = " ".join(map(str, t.head(10).values.flatten())).lower()
        sig = cols + " " + body
        if any(k in sig for k in ["entidad", "nomenclatura", "objeto", "descrip", "publicacion", "publicación", "version seace", "versión seace", "acciones"]):
            candidates.append(t)
    if candidates:
        return max(candidates, key=lambda x: (len(x), len(x.columns)))
    return pd.DataFrame()


def _normalize(df):
    if df.empty: return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [" ".join(str(x) for x in col if str(x) != "nan").strip() for col in df.columns]
    df = df.copy(); df.columns = [" ".join(str(c).split()) for c in df.columns]
    return df


def search_seace_public_browser(url=SEACE_PUBLIC_URL, keyword="satelital", year="2026", version="Seace 3", headless=False, max_wait=20) -> Tuple[pd.DataFrame, List[str]]:
    diagnostics: List[str] = []
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--ignore-certificate-errors")
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, max_wait)
        driver.get(url)
        diagnostics.append(f"GET navegador: {url}")

        # Espera el campo principal del Buscador de Procedimientos.
        desc_id = f"{PROCESS_FORM}:descripcionObjeto"
        wait.until(EC.presence_of_element_located((By.ID, desc_id)))

        # Activar pestaña de procedimientos en estado JSF si existe.
        driver.execute_script("""
            const active = document.getElementById('tbBuscador_activeIndex');
            if (active) active.value = '1';
        """)

        _set_value_js(driver, desc_id, keyword)
        _set_value_js(driver, f"{PROCESS_FORM}:anioConvocatoria_input", str(year))
        _set_value_js(driver, f"{PROCESS_FORM}:anioConvocatoria_focus", str(year))
        _set_value_js(driver, f"{PROCESS_FORM}:j_idt247_input", _version_value(version))

        diagnostics.append(f"Descripción: {keyword}")
        diagnostics.append(f"Año: {year}")
        diagnostics.append(f"Versión: {_version_value(version)}")

        # Intentar botones reales en orden: sin token primero porque es el botón visible que manualmente funciona en algunos casos.
        button_ids = [
            f"{PROCESS_FORM}:btnBuscarSel",
            f"{PROCESS_FORM}:btnBuscarSelToken",
        ]
        clicked = False
        for bid in button_ids:
            if _click_if_exists(driver, bid):
                diagnostics.append(f"Click botón: {bid}")
                clicked = True
                break
        if not clicked:
            diagnostics.append("No se encontró botón Buscar por ID; intentando submit por JS")
            driver.execute_script("document.getElementById(arguments[0]).submit();", PROCESS_FORM)

        # Esperar a que la página procese. Buscamos texto esperado o tabla con datos.
        end_time = time.time() + max_wait
        last_len = 0
        html = driver.page_source
        while time.time() < end_time:
            time.sleep(1)
            html = driver.page_source
            if len(html) != last_len:
                last_len = len(html)
            df = _normalize(_parse_tables(html))
            if not df.empty and len(df) > 0:
                with open("respuesta_seace_browser.html", "w", encoding="utf-8", errors="ignore") as f:
                    f.write(html)
                diagnostics.append(f"Tabla detectada navegador: {len(df)} filas / {len(df.columns)} columnas")
                return df, diagnostics

        with open("respuesta_seace_browser.html", "w", encoding="utf-8", errors="ignore") as f:
            f.write(html)
        diagnostics.append("No se detectó tabla con navegador. Se guardó respuesta_seace_browser.html")
        return pd.DataFrame(), diagnostics
    except Exception as e:
        diagnostics.append(f"Error navegador: {type(e).__name__} - {e}")
        return pd.DataFrame(), diagnostics
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
