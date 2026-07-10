import streamlit as st
import pandas as pd
from src.normalizer import normalize_columns
from src.scoring import enriquecer_oportunidades
from src.exporter import build_excel
from src.seace_browser_scraper import search_seace_public_browser, SEACE_PUBLIC_URL
from src.seace_public_scraper import search_seace_public
from src.oece_massive_connector import download_any_dataset, fetch_massive_by_params, DEFAULT_PORTAL_URL

st.set_page_config(page_title="SEACE Radar Gov Peru v9.2", layout="wide")

# =============================
# Session state v9.2
# =============================
if "raw_data" not in st.session_state:
    st.session_state.raw_data = None
if "diagnostics" not in st.session_state:
    st.session_state.diagnostics = []
if "df_final" not in st.session_state:
    st.session_state.df_final = None
if "excel_bytes" not in st.session_state:
    st.session_state.excel_bytes = None
if "last_filter_key" not in st.session_state:
    st.session_state.last_filter_key = None

@st.cache_data(show_spinner=False)
def generar_excel(df: pd.DataFrame) -> bytes:
    return build_excel(df)


def reset_resultados():
    st.session_state.raw_data = None
    st.session_state.diagnostics = []
    st.session_state.df_final = None
    st.session_state.excel_bytes = None
    st.session_state.last_filter_key = None


def estado_orden(valor: str) -> int:
    orden = {
        "Vigente para Consultas y Propuesta": 1,
        "Vigente sólo para Propuesta": 2,
        "Vigente solo para Propuesta": 2,
        "En Evaluación": 3,
        "En Evaluacion": 3,
        "Revisar": 4,
        "Cerrado": 5,
    }
    return orden.get(str(valor), 99)


st.title("SEACE Radar Gov Peru v9.2 - Calidad de datos y persistencia")
st.caption("SEACE automático + cronograma por etapa + vigencia comercial + filtros persistentes + exportación estable.")

source = st.sidebar.radio("Fuente de datos", [
    "SEACE Público - navegador automático",
    "SEACE Público - requests experimental",
    "Auto OECE - descarga construida",
    "URL pública directa",
    "Archivo local CSV/XLSX",
])

with st.sidebar:
    st.divider()
    if st.button("Limpiar resultados guardados"):
        reset_resultados()
        st.rerun()

raw = st.session_state.raw_data
diagnostics = st.session_state.diagnostics

# =============================
# Fuentes
# =============================
if source == "SEACE Público - navegador automático":
    url = st.sidebar.text_input("URL Buscador SEACE", SEACE_PUBLIC_URL)
    keyword = st.sidebar.text_input("Descripción / palabra clave", "satelital")
    year = st.sidebar.text_input("Año convocatoria", "2026")
    version = st.sidebar.selectbox("Versión SEACE", ["Seace 3", "Seace 2", ""], index=0)
    headless = not st.sidebar.checkbox("Navegador visible", value=True)
    max_wait = st.sidebar.slider("Espera de resultados (segundos)", 5, 120, 45)
    enrich_details = st.sidebar.checkbox("Enriquecer con detalle (RUC y cronograma)", value=True)
    max_details = st.sidebar.slider("Máximo detalles a revisar", 1, 30, 15)

    if st.sidebar.button("Buscar con navegador"):
        with st.spinner("Consultando SEACE Público y leyendo cronogramas..."):
            raw, diagnostics = search_seace_public_browser(
                url=url,
                keyword=keyword,
                year=year,
                version=version,
                headless=headless,
                max_wait=max_wait,
                enrich_details=enrich_details,
                max_details=max_details,
            )
            st.session_state.raw_data = raw
            st.session_state.diagnostics = diagnostics
            st.session_state.excel_bytes = None
            st.session_state.df_final = None

elif source == "SEACE Público - requests experimental":
    url = st.sidebar.text_input("URL Buscador SEACE", SEACE_PUBLIC_URL)
    keyword = st.sidebar.text_input("Descripción / palabra clave", "satelital")
    year = st.sidebar.text_input("Año convocatoria", "2026")
    version = st.sidebar.selectbox("Versión SEACE", ["Seace 3", "Seace 2", ""], index=0)
    if st.sidebar.button("Buscar con requests"):
        raw, diagnostics = search_seace_public(url=url, keyword=keyword, objeto="", year=year, version=version)
        st.session_state.raw_data = raw
        st.session_state.diagnostics = diagnostics
        st.session_state.excel_bytes = None
        st.session_state.df_final = None

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
        st.session_state.raw_data = raw
        st.session_state.diagnostics = diagnostics
        st.session_state.excel_bytes = None
        st.session_state.df_final = None

elif source == "URL pública directa":
    url = st.sidebar.text_input("URL directa CSV/XLSX/JSON/JSONL/GZ/ZIP/TAR.GZ")
    keyword_hint = st.sidebar.text_input("Keyword posterior", "satelital")
    if st.sidebar.button("Descargar URL") and url:
        raw, msg = download_any_dataset(url)
        diagnostics = [msg]
        if raw is not None and not raw.empty and keyword_hint:
            raw = raw[raw.astype(str).apply(lambda s: s.str.lower().str.contains(keyword_hint.lower(), na=False)).any(axis=1)]
        st.session_state.raw_data = raw
        st.session_state.diagnostics = diagnostics
        st.session_state.excel_bytes = None
        st.session_state.df_final = None

else:
    uploaded = st.sidebar.file_uploader("Carga CSV o Excel", type=["csv", "xlsx", "xls"])
    if uploaded:
        raw = pd.read_csv(uploaded) if uploaded.name.lower().endswith(".csv") else pd.read_excel(uploaded, engine="openpyxl")
        diagnostics = [f"Archivo cargado: {uploaded.name}"]
        st.session_state.raw_data = raw
        st.session_state.diagnostics = diagnostics
        st.session_state.excel_bytes = None
        st.session_state.df_final = None

# =============================
# Diagnóstico
# =============================
if diagnostics:
    with st.expander("Diagnóstico", expanded=False):
        for d in diagnostics:
            st.write(d)

# =============================
# Dashboard
# =============================
if raw is not None and not raw.empty:
    df = normalize_columns(raw)
    if "fecha_publicacion" in df.columns:
        df = df.sort_values(by="fecha_publicacion", ascending=False, na_position="last")
    df = enriquecer_oportunidades(df)

    if "estado_comercial" in df.columns:
        df["orden_estado"] = df["estado_comercial"].apply(estado_orden)
    else:
        df["orden_estado"] = 99

    st.subheader("Dashboard ejecutivo")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Registros", len(df))
    c2.metric("Consultas + Propuesta", int((df.get("estado_comercial", "") == "Vigente para Consultas y Propuesta").sum()) if "estado_comercial" in df else 0)
    c3.metric("Sólo Propuesta", int((df.get("estado_comercial", "") == "Vigente sólo para Propuesta").sum()) if "estado_comercial" in df else 0)
    c4.metric("Evaluación", int((df.get("estado_comercial", "") == "En Evaluación").sum()) if "estado_comercial" in df else 0)
    c5.metric("Cerrados", int((df.get("estado_comercial", "") == "Cerrado").sum()) if "estado_comercial" in df else 0)
    c6.metric("Monto potencial", f"S/ {df['monto'].sum():,.0f}" if "monto" in df else "S/ 0")

    st.subheader("Filtros")
    f1, f2, f3, f4, f5 = st.columns(5)
    kw = f1.text_input("Palabra clave", "satelital")
    pri_options = ["A", "B", "C"]
    pri = f2.multiselect("Prioridad", pri_options, default=pri_options)
    estado_options = sorted(df["estado_comercial"].dropna().unique().tolist()) if "estado_comercial" in df else []
    estado = f3.multiselect("Estado comercial", estado_options, default=[])
    sec_options = sorted(df["sector"].dropna().unique().tolist()) if "sector" in df else []
    sec = f4.multiselect("Sector", sec_options, default=[])
    reg = f5.text_input("Región contiene")

    filtered = df.copy()
    if kw:
        filtered = filtered[filtered.astype(str).apply(lambda s: s.str.lower().str.contains(kw.lower(), na=False)).any(axis=1)]
    if pri and "prioridad" in filtered:
        filtered = filtered[filtered["prioridad"].isin(pri)]
    if estado and "estado_comercial" in filtered:
        filtered = filtered[filtered["estado_comercial"].isin(estado)]
    if sec and "sector" in filtered:
        filtered = filtered[filtered["sector"].isin(sec)]
    if reg and "region" in filtered:
        filtered = filtered[filtered["region"].astype(str).str.lower().str.contains(reg.lower(), na=False)]

    sort_cols = [c for c in ["orden_estado", "dias_para_propuesta", "fecha_publicacion"] if c in filtered.columns]
    if sort_cols:
        ascending = [True if c != "fecha_publicacion" else False for c in sort_cols]
        filtered = filtered.sort_values(by=sort_cols, ascending=ascending, na_position="last")

    st.session_state.df_final = filtered

    cols = [c for c in [
        "vigencia", "estado_comercial", "fecha_publicacion", "consulta_fin", "propuesta_fin", "buena_pro_fin",
        "dias_para_consulta", "dias_para_propuesta", "ruc", "entidad", "sector", "region", "nomenclatura",
        "objeto", "descripcion", "monto", "moneda", "version_seace", "consulta_inicio", "propuesta_inicio",
        "buena_pro_inicio", "convocatoria_inicio", "convocatoria_fin", "registro_inicio", "registro_fin",
        "evaluacion_inicio", "evaluacion_fin", "direccion_legal", "telefono_entidad", "motivos_score",
        "semaforo", "prioridad", "score", "url_detalle"
    ] if c in filtered.columns]

    st.subheader("Oportunidades")
    st.dataframe(filtered[cols], width="stretch")

    filter_key = str(filtered.shape) + "|" + str(filtered.index.tolist())
    if st.session_state.last_filter_key != filter_key:
        st.session_state.excel_bytes = generar_excel(filtered)
        st.session_state.last_filter_key = filter_key

    st.download_button(
        "Descargar Excel ejecutivo",
        data=st.session_state.excel_bytes,
        file_name="SEACE_Radar_v9_2_Cronograma_Vigencia.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("Selecciona una fuente. Para automático usa SEACE Público - navegador automático.")
