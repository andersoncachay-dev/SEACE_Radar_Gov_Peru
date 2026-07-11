import streamlit as st
import pandas as pd
from pathlib import Path

from src.normalizer import normalize_columns
from src.scoring import enriquecer_oportunidades
from src.exporter import build_excel
from src.seace_browser_scraper import search_seace_public_browser, SEACE_PUBLIC_URL
from src.seace_public_scraper import search_seace_public
from src.oece_massive_connector import download_any_dataset, fetch_massive_by_params, DEFAULT_PORTAL_URL
from src.seace_menor8_scraper import search_menor8_browser, MENOR8_SEARCH_URL, MENOR8_AUTH_URL

st.set_page_config(page_title="SEACE Radar Gov Peru v10.6", layout="wide")

for key, default in {
    "raw_publico": None,
    "raw_menor8": None,
    "diagnostics_publico": [],
    "diagnostics_menor8": [],
    "df_final": None,
    "excel_bytes": None,
    "last_filter_key": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

@st.cache_data(show_spinner=False)
def generar_excel(df: pd.DataFrame) -> bytes:
    return build_excel(df)

def reset_resultados():
    for k in ["raw_publico", "raw_menor8", "diagnostics_publico", "diagnostics_menor8", "df_final", "excel_bytes", "last_filter_key"]:
        st.session_state[k] = None if k not in ["diagnostics_publico", "diagnostics_menor8"] else []

def estado_orden(valor: str) -> int:
    orden = {
        "Vence Hoy": 0,
        "Vigente": 1,
        "Vigente para Consultas y Propuesta": 1,
        "Vigente para Consulta y Cotización": 1,
        "Vigente sólo para Propuesta": 2,
        "Vigente solo para Propuesta": 2,
        "Vigente sólo para Cotización": 2,
        "Vigente solo para Cotización": 2,
        "En Evaluación": 3,
        "En Evaluacion": 3,
        "Revisar": 4,
        "Cerrado": 5,
    }
    return orden.get(str(valor), 99)

def preparar_publico(raw: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(raw)
    df["origen"] = "SEACE_PUBLICO"
    if "fecha_publicacion" in df.columns:
        df = df.sort_values(by="fecha_publicacion", ascending=False, na_position="last")
    return df

def preparar_menor8(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df["origen"] = "MENOR_8_UIT"
    rename = {
        "codigo": "nomenclatura",
        "entidad_contratante": "entidad",
        "tipo_objeto": "objeto",
        "descripcion": "descripcion",
        "monto_estimado": "monto",
        "moneda": "moneda",
        "detalle_url": "url_detalle",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    if "monto" not in df.columns:
        df["monto"] = 0
    df["monto"] = pd.to_numeric(df["monto"], errors="coerce").fillna(0)
    for c in [
        "fecha_publicacion", "consulta_inicio", "consulta_fin", "cotizacion_inicio", "cotizacion_fin",
        "propuesta_inicio", "propuesta_fin", "buena_pro_inicio", "buena_pro_fin",
    ]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce", dayfirst=True)
    if "cotizacion_inicio" in df.columns:
        df["propuesta_inicio"] = df["cotizacion_inicio"]
    if "cotizacion_fin" in df.columns:
        df["propuesta_fin"] = df["cotizacion_fin"]
    return df

st.title("SEACE Radar Gov Peru v10.6 - Público + Menores a 8 UIT")
st.caption("Radar comercial Hughes/Starlink para SEACE Público y Contratos Menores a 8 UIT, con cronograma robusto y descarga de requerimientos PDF.")

source = st.sidebar.radio("Fuente de datos", [
    "SEACE Público", "Menores a 8 UIT", "Ambos módulos",
    "SEACE Público - requests experimental", "Auto OECE - descarga construida",
    "URL pública directa", "Archivo local CSV/XLSX",
])

with st.sidebar:
    st.divider()
    if st.button("Limpiar resultados guardados"):
        reset_resultados()
        st.rerun()

if source in ["SEACE Público", "Ambos módulos"]:
    st.sidebar.subheader("SEACE Público")
    url_publico = st.sidebar.text_input("URL Buscador SEACE Público", SEACE_PUBLIC_URL)
    keyword_publico = st.sidebar.text_input("Palabra clave público", "satelital")
    year_publico = st.sidebar.text_input("Año convocatoria", "2026")
    version_publico = st.sidebar.selectbox("Versión SEACE", ["Seace 3", "Seace 2", ""], index=0)
    headless_publico = not st.sidebar.checkbox("Navegador visible público", value=True)
    max_wait_publico = st.sidebar.slider("Espera público (segundos)", 5, 120, 45)
    enrich_publico = st.sidebar.checkbox("Enriquecer público con detalle", value=True)
    max_details_publico = st.sidebar.slider("Máximo detalles público", 1, 30, 15)
    if st.sidebar.button("Buscar SEACE Público"):
        with st.spinner("Consultando SEACE Público..."):
            raw, diag = search_seace_public_browser(
                url=url_publico, keyword=keyword_publico, year=year_publico,
                version=version_publico, headless=headless_publico,
                max_wait=max_wait_publico, enrich_details=enrich_publico,
                max_details=max_details_publico,
            )
            st.session_state.raw_publico = raw
            st.session_state.diagnostics_publico = diag
            st.session_state.excel_bytes = None
            st.session_state.df_final = None
            st.session_state.last_filter_key = None

if source in ["Menores a 8 UIT", "Ambos módulos"]:
    st.sidebar.subheader("Menores a 8 UIT")
    auth_url = st.sidebar.text_input("URL Login Menores", MENOR8_AUTH_URL)
    search_url = st.sidebar.text_input("URL Buscador Menores", MENOR8_SEARCH_URL)
    keyword_menor8 = st.sidebar.text_input("Palabra clave menores", "satelital")
    headless_menor8 = not st.sidebar.checkbox("Navegador visible menores", value=True)
    max_wait_menor8 = st.sidebar.slider("Espera menores (segundos)", 5, 180, 60)
    login_wait_seconds = st.sidebar.slider("Espera login manual (segundos)", 60, 600, 300, step=30)
    max_results_menor8 = st.sidebar.slider("Máximo contratos menores", 5, 100, 50)
    enrich_menor8 = st.sidebar.checkbox("Leer detalle menores", value=True)
    download_requirements = st.sidebar.checkbox("Descargar PDFs/TDR automáticamente", value=True)
    st.sidebar.info("Para Menores a 8 UIT, abre navegador visible. Si aparece login, inicia sesión manualmente; el scraper continúa desde la sesión abierta, acepta términos si aparecen y descarga PDFs si está activado.")
    if st.sidebar.button("Buscar Menores a 8 UIT"):
        with st.spinner("Consultando Contratos Menores a 8 UIT..."):
            raw, diag = search_menor8_browser(
                auth_url=auth_url, search_url=search_url, keyword=keyword_menor8,
                headless=headless_menor8, max_wait=max_wait_menor8,
                login_wait_seconds=login_wait_seconds, max_results=max_results_menor8,
                enrich_details=enrich_menor8, download_requirements=download_requirements,
            )
            st.session_state.raw_menor8 = raw
            st.session_state.diagnostics_menor8 = diag
            st.session_state.excel_bytes = None
            st.session_state.df_final = None
            st.session_state.last_filter_key = None

if source == "SEACE Público - requests experimental":
    url = st.sidebar.text_input("URL Buscador SEACE", SEACE_PUBLIC_URL)
    keyword = st.sidebar.text_input("Descripción / palabra clave", "satelital")
    year = st.sidebar.text_input("Año convocatoria", "2026")
    version = st.sidebar.selectbox("Versión SEACE", ["Seace 3", "Seace 2", ""], index=0)
    if st.sidebar.button("Buscar con requests"):
        raw, diagnostics = search_seace_public(url=url, keyword=keyword, objeto="", year=year, version=version)
        st.session_state.raw_publico = raw
        st.session_state.diagnostics_publico = diagnostics
        st.session_state.excel_bytes = None
        st.session_state.last_filter_key = None
elif source == "Auto OECE - descarga construida":
    base_url = st.sidebar.text_input("Portal API OECE", DEFAULT_PORTAL_URL)
    source_name = st.sidebar.text_input("source", "ocds")
    file_type = st.sidebar.selectbox("type", ["csv", "excel", "xlsx", "json", "jsonl"], index=0)
    year = st.sidebar.text_input("year", "2026")
    month = st.sidebar.text_input("month", "")
    keyword_hint = st.sidebar.text_input("Keyword posterior", "satelital")
    if st.sidebar.button("Conectar y descargar automáticamente"):
        raw, diagnostics = fetch_massive_by_params(base_url, source_name, file_type, year, month)
        if raw is not None and not raw.empty and keyword_hint:
            raw = raw[raw.astype(str).apply(lambda s: s.str.lower().str.contains(keyword_hint.lower(), na=False)).any(axis=1)]
        st.session_state.raw_publico = raw
        st.session_state.diagnostics_publico = diagnostics
        st.session_state.excel_bytes = None
        st.session_state.last_filter_key = None
elif source == "URL pública directa":
    url = st.sidebar.text_input("URL directa CSV/XLSX/JSON/JSONL/GZ/ZIP/TAR.GZ")
    keyword_hint = st.sidebar.text_input("Keyword posterior", "satelital")
    if st.sidebar.button("Descargar URL") and url:
        raw, msg = download_any_dataset(url)
        diagnostics = [msg]
        if raw is not None and not raw.empty and keyword_hint:
            raw = raw[raw.astype(str).apply(lambda s: s.str.lower().str.contains(keyword_hint.lower(), na=False)).any(axis=1)]
        st.session_state.raw_publico = raw
        st.session_state.diagnostics_publico = diagnostics
        st.session_state.excel_bytes = None
        st.session_state.last_filter_key = None
elif source == "Archivo local CSV/XLSX":
    uploaded = st.sidebar.file_uploader("Carga CSV o Excel", type=["csv", "xlsx", "xls"])
    if uploaded:
        raw = pd.read_csv(uploaded) if uploaded.name.lower().endswith(".csv") else pd.read_excel(uploaded, engine="openpyxl")
        st.session_state.raw_publico = raw
        st.session_state.diagnostics_publico = [f"Archivo cargado: {uploaded.name}"]
        st.session_state.excel_bytes = None
        st.session_state.last_filter_key = None

if st.session_state.diagnostics_publico or st.session_state.diagnostics_menor8:
    with st.expander("Diagnóstico", expanded=False):
        if st.session_state.diagnostics_publico:
            st.write("### SEACE Público")
            for d in st.session_state.diagnostics_publico:
                st.write(d)
        if st.session_state.diagnostics_menor8:
            st.write("### Menores a 8 UIT")
            for d in st.session_state.diagnostics_menor8:
                st.write(d)

frames = []
if st.session_state.raw_publico is not None and not st.session_state.raw_publico.empty:
    try:
        frames.append(preparar_publico(st.session_state.raw_publico))
    except Exception as e:
        st.warning(f"No se pudo preparar SEACE Público: {e}")
if st.session_state.raw_menor8 is not None and not st.session_state.raw_menor8.empty:
    try:
        frames.append(preparar_menor8(st.session_state.raw_menor8))
    except Exception as e:
        st.warning(f"No se pudo preparar Menores a 8 UIT: {e}")

if frames:
    df = pd.concat(frames, ignore_index=True, sort=False)
    df = enriquecer_oportunidades(df)
    if "estado_operativo" in df.columns:
        df["orden_estado"] = df["estado_operativo"].apply(estado_orden)
    elif "estado_comercial" in df.columns:
        df["orden_estado"] = df["estado_comercial"].apply(estado_orden)
    else:
        df["orden_estado"] = 99

    st.subheader("Dashboard ejecutivo")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total", len(df))
    c2.metric("SEACE Público", int((df.get("origen", "") == "SEACE_PUBLICO").sum()) if "origen" in df else 0)
    c3.metric("Menores 8 UIT", int((df.get("origen", "") == "MENOR_8_UIT").sum()) if "origen" in df else 0)
    accionables_count = (int(df["estado_operativo"].astype(str).isin(["Vence Hoy", "Vigente"]).sum()) if "estado_operativo" in df else int(df.get("estado_comercial", pd.Series(dtype=str)).astype(str).str.contains("Vigente", na=False).sum()) if "estado_comercial" in df else 0)
    c4.metric("Accionables", accionables_count)
    cerrados_count = int((df["estado_operativo"].astype(str) == "Cerrado").sum()) if "estado_operativo" in df else int((df.get("estado_comercial", "") == "Cerrado").sum()) if "estado_comercial" in df else 0
    c5.metric("Cerrados", cerrados_count)
    c6.metric("Monto", f"S/ {pd.to_numeric(df.get('monto', 0), errors='coerce').fillna(0).sum():,.0f}")

    st.subheader("Filtros")
    f1, f2, f3, f4, f5, f6 = st.columns(6)
    kw = f1.text_input("Palabra clave", "satelital")
    origen_options = sorted(df["origen"].dropna().unique().tolist()) if "origen" in df else []
    origen = f2.multiselect("Origen", origen_options, default=origen_options)
    pri_options = ["A", "B", "C"]
    pri = f3.multiselect("Prioridad", pri_options, default=pri_options)
    estado_options = sorted(df["estado_operativo"].dropna().unique().tolist()) if "estado_operativo" in df else sorted(df["estado_comercial"].dropna().unique().tolist()) if "estado_comercial" in df else []
    estado = f4.multiselect("Estado", estado_options, default=[])
    sec_options = sorted(df["sector"].dropna().unique().tolist()) if "sector" in df else []
    sec = f5.multiselect("Sector", sec_options, default=[])
    reg = f6.text_input("Región contiene")

    filtered = df.copy()
    if kw:
        filtered = filtered[filtered.astype(str).apply(lambda s: s.str.lower().str.contains(kw.lower(), na=False)).any(axis=1)]
    if origen and "origen" in filtered:
        filtered = filtered[filtered["origen"].isin(origen)]
    if pri and "prioridad" in filtered:
        filtered = filtered[filtered["prioridad"].isin(pri)]
    if estado:
        if "estado_operativo" in filtered:
            filtered = filtered[filtered["estado_operativo"].isin(estado)]
        elif "estado_comercial" in filtered:
            filtered = filtered[filtered["estado_comercial"].isin(estado)]
    if sec and "sector" in filtered:
        filtered = filtered[filtered["sector"].isin(sec)]
    if reg and "region" in filtered:
        filtered = filtered[filtered["region"].astype(str).str.lower().str.contains(reg.lower(), na=False)]

    sort_cols = [c for c in ["orden_estado", "dias_para_cotizacion", "dias_para_propuesta", "propuesta_fin", "fecha_publicacion"] if c in filtered.columns]
    if sort_cols:
        ascending = [True if c != "fecha_publicacion" else False for c in sort_cols]
        filtered = filtered.sort_values(by=sort_cols, ascending=ascending, na_position="last")

    st.session_state.df_final = filtered
    cols = [c for c in [
        "origen", "estado_operativo", "vigencia", "estado_comercial", "estado_portal",
        "fecha_publicacion", "consulta_inicio", "consulta_fin", "cotizacion_inicio", "cotizacion_fin", "propuesta_fin",
        "dias_para_consulta", "dias_para_cotizacion", "dias_para_propuesta",
        "horas_para_consulta", "horas_para_cotizacion", "situacion_consulta", "situacion_cotizacion",
        "ruc", "entidad", "sector", "region", "nomenclatura", "objeto", "descripcion", "area_usuaria",
        "monto", "moneda", "version_seace", "requerimiento_pdf", "requerimiento_pdf_nombre",
        "requerimiento_pdf_local", "requerimiento_pdf_archivo", "motivos_score", "semaforo", "prioridad", "score", "url_detalle",
    ] if c in filtered.columns]

    st.subheader("Oportunidades")

    # Eliminar columnas duplicadas del dataframe
    filtered = filtered.loc[:, ~filtered.columns.duplicated()].copy()

    # Eliminar nombres repetidos de la lista cols
    cols = list(dict.fromkeys(cols))

    # Mantener solo columnas existentes
    cols = [c for c in cols if c in filtered.columns]
    st.dataframe(filtered[cols], width="stretch")

    if "requerimiento_pdf_local" in filtered.columns:
        pdf_df = filtered[filtered["requerimiento_pdf_local"].notna() & (filtered["requerimiento_pdf_local"].astype(str) != "")].copy()
        if not pdf_df.empty:
            st.subheader("Descarga de requerimientos PDF")
            labels = []
            lookup = {}
            for _, r in pdf_df.iterrows():
                label = f"{r.get('nomenclatura','')} | {str(r.get('entidad',''))[:60]} | {r.get('requerimiento_pdf_archivo','requerimiento.pdf')}"
                labels.append(label)
                lookup[label] = r
            selected_label = st.selectbox("Selecciona el requerimiento a descargar", labels, key="pdf_req_selector")
            selected_row = lookup[selected_label]
            pdf_path = Path(str(selected_row.get("requerimiento_pdf_local", "")))
            if pdf_path.exists():
                st.download_button("Descargar PDF del requerimiento", data=pdf_path.read_bytes(), file_name=str(selected_row.get("requerimiento_pdf_archivo", pdf_path.name)), mime="application/pdf")
            else:
                st.warning("El PDF figura en la tabla, pero no se encuentra el archivo local. Ejecuta nuevamente con 'Leer detalle menores' y 'Descargar PDFs/TDR automáticamente' activados.")

    filter_key = str(filtered.shape) + "|" + str(filtered.index.tolist()) + "|" + str(filtered.columns.tolist())
    if st.session_state.last_filter_key != filter_key:
        st.session_state.excel_bytes = generar_excel(filtered)
        st.session_state.last_filter_key = filter_key

    st.download_button("Descargar Excel ejecutivo", data=st.session_state.excel_bytes, file_name="SEACE_Radar_v10_5_Publico_Menores8UIT.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
else:
    st.info("Ejecuta una búsqueda en SEACE Público, Menores a 8 UIT o Ambos módulos.")
